import asyncio
import logging
import sqlite3
import time
from datetime import datetime, timezone

import httpx

from linksync import linkora, readeck, state
from linksync.config import Config

logger = logging.getLogger(__name__)


def readeck_timestamp_to_epoch(timestamp: str) -> float:
    """Convert Readeck ISO 8601 timestamp to epoch seconds for comparison."""
    return datetime.fromisoformat(timestamp).timestamp()


async def run_sync(config: Config, connection: sqlite3.Connection) -> None:
    """Run the complete six-phase sync cycle between Linkora and Readeck."""
    
    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {config.linkora.token}"},
        verify=config.linkora.verify_tls,
    ) as linkora_client, httpx.AsyncClient(
        headers={"Authorization": f"Bearer {config.readeck.token}"}
    ) as readeck_client:
        
        # Phase 1: Initialization
        logger.info("Phase 1: Initialization")
        
        linkora_folder_id_str = state.get_state(connection, "linkora_folder_id")
        if linkora_folder_id_str is None:
            root_folders = await linkora.get_root_folders(linkora_client, config.linkora.url)
            folder = next((f for f in root_folders if f["name"] == config.sync.folder_name), None)
            
            if folder is None:
                folder_id = await linkora.create_folder(linkora_client, config.linkora.url, config.sync.folder_name)
                logger.info(f"Created sync folder '{config.sync.folder_name}' with ID {folder_id}")
            else:
                folder_id = folder["id"]
                logger.info(f"Found existing sync folder '{config.sync.folder_name}' with ID {folder_id}")
            
            state.set_state(connection, "linkora_folder_id", str(folder_id))
            linkora_folder_id = folder_id
        else:
            linkora_folder_id = int(linkora_folder_id_str)
        
        linkora_last_sync_str = state.get_state(connection, "linkora_last_sync")
        linkora_last_sync = int(linkora_last_sync_str) if linkora_last_sync_str else 0
        
        readeck_last_sync = state.get_state(connection, "readeck_last_sync")
        
        # Phase 2: Fetch changes
        logger.info("Phase 2: Fetch changes")
        
        linkora_updates, linkora_tombstones = await asyncio.gather(
            linkora.get_updates(linkora_client, config.linkora.url, linkora_last_sync),
            linkora.get_tombstones(linkora_client, config.linkora.url, linkora_last_sync),
        )
        
        readeck_changes = await readeck.get_sync_changes(readeck_client, config.readeck.url, readeck_last_sync)
        
        readeck_updates = [change for change in readeck_changes if change["type"] == "update"]
        readeck_deletions = [change for change in readeck_changes if change["type"] == "delete"]
        
        readeck_bookmarks = []
        for change in readeck_updates:
            bookmark = await readeck.get_bookmark(readeck_client, config.readeck.url, change["id"])
            readeck_bookmarks.append(bookmark)
        
        # Phase 3: Process deletions
        logger.info("Phase 3: Process deletions")
        
        for tombstone in linkora_tombstones:
            if tombstone["operation"] != "DELETE_A_LINK":
                continue
            
            link_id = tombstone["payload"]["id"]
            try:
                mapping = state.get_mapping_by_linkora_id(connection, link_id)
                
                if mapping is None:
                    continue
                
                linkora_id, readeck_uid, url = mapping
                await readeck.delete_bookmark(readeck_client, config.readeck.url, readeck_uid)
                state.remove_mapping_by_linkora_id(connection, linkora_id)
                logger.info(f"Deleted bookmark {readeck_uid} (Linkora link {link_id})")
            except Exception as error:
                logger.warning(f"Failed to process Linkora deletion for link {link_id}: {error}")
        
        for deletion in readeck_deletions:
            readeck_uid = deletion["id"]
            try:
                mapping = state.get_mapping_by_readeck_uid(connection, readeck_uid)
                
                if mapping is None:
                    continue
                
                linkora_id, _, url = mapping
                await linkora.delete_link(linkora_client, config.linkora.url, linkora_id)
                state.remove_mapping_by_readeck_uid(connection, readeck_uid)
                logger.info(f"Deleted link {linkora_id} (Readeck bookmark {readeck_uid})")
            except Exception as error:
                logger.warning(f"Failed to process Readeck deletion for bookmark {readeck_uid}: {error}")
        
        # Phase 4: Process tag changes
        logger.info("Phase 4: Process tag changes")
        
        linkora_tags = await linkora.get_tags(linkora_client, config.linkora.url)
        readeck_labels = await readeck.get_labels(readeck_client, config.readeck.url)
        existing_tag_mappings = state.get_all_tag_mappings(connection)
        
        tag_mappings_dict = {tag_id: label_name for tag_id, label_name in existing_tag_mappings}
        
        for tag in linkora_tags:
            tag_id = tag["id"]
            tag_name = tag["name"]
            
            if tag_id not in tag_mappings_dict:
                state.add_tag_mapping(connection, tag_id, tag_name)
                logger.info(f"Added new tag mapping: Linkora tag {tag_id} -> '{tag_name}'")
            elif tag_mappings_dict[tag_id] != tag_name:
                old_name = tag_mappings_dict[tag_id]
                await readeck.rename_label(readeck_client, config.readeck.url, old_name, tag_name)
                state.update_tag_mapping_name(connection, tag_id, tag_name)
                logger.info(f"Renamed label '{old_name}' -> '{tag_name}' (Linkora tag {tag_id})")
        
        for label in readeck_labels:
            label_name = label["name"]
            tag_id = state.get_tag_mapping_by_name(connection, label_name)
            
            if tag_id is None:
                new_tag_id = await linkora.create_tag(linkora_client, config.linkora.url, label_name)
                state.add_tag_mapping(connection, new_tag_id, label_name)
                logger.info(f"Created new tag '{label_name}' in Linkora with ID {new_tag_id}")
        
        # Phase 5: Process bookmark creates and updates
        logger.info("Phase 5: Process bookmark creates and updates")
        
        linkora_updated_urls = {}
        
        # Step 15: Linkora → Readeck
        for link in linkora_updates["links"]:
            if link["idOfLinkedFolder"] != linkora_folder_id:
                continue
            
            try:
                url = link["url"]
                linkora_updated_urls[url] = link
                mapping = state.get_mapping_by_url(connection, url)
                
                if mapping is not None:
                    linkora_id, readeck_uid, _ = mapping
                    
                    bookmark = await readeck.get_bookmark(readeck_client, config.readeck.url, readeck_uid)
                    linkora_timestamp = link["eventTimestamp"]
                    readeck_timestamp = readeck_timestamp_to_epoch(bookmark["updated"])
                    
                    if linkora_timestamp > readeck_timestamp:
                        label_names = []
                        for link_tag in linkora_updates["linkTags"]:
                            if link_tag["linkId"] == link["id"]:
                                tag_id = link_tag["tagId"]
                                label_name = state.get_tag_mapping_by_id(connection, tag_id)
                                if label_name:
                                    label_names.append(label_name)
                        
                        fields = {
                            "title": link["title"],
                            "description": link["note"],
                            "labels": label_names,
                            "is_marked": link["markedAsImportant"],
                        }
                        await readeck.update_bookmark(readeck_client, config.readeck.url, readeck_uid, fields)
                        logger.info(f"Updated Readeck bookmark {readeck_uid} from Linkora link {link['id']}")
                else:
                    label_names = []
                    for link_tag in linkora_updates["linkTags"]:
                        if link_tag["linkId"] == link["id"]:
                            tag_id = link_tag["tagId"]
                            label_name = state.get_tag_mapping_by_id(connection, tag_id)
                            if label_name:
                                label_names.append(label_name)
                    
                    readeck_uid = await readeck.create_bookmark(
                        readeck_client, config.readeck.url, url, link["title"], label_names
                    )
                    state.add_mapping(connection, link["id"], readeck_uid, url)
                    logger.info(f"Created Readeck bookmark {readeck_uid} from Linkora link {link['id']}")
            except Exception as error:
                logger.warning(f"Failed to process Linkora link {link['id']}: {error}")
        
        # Step 16: Readeck → Linkora
        readeck_last_sync_epoch = (
            readeck_timestamp_to_epoch(readeck_last_sync) if readeck_last_sync else 0.0
        )

        for bookmark in readeck_bookmarks:
            if bookmark.get("is_archived") or bookmark.get("is_deleted"):
                continue
            
            try:
                url = bookmark["url"]
                mapping = state.get_mapping_by_url(connection, url)
                
                if mapping is not None:
                    linkora_id, readeck_uid, _ = mapping
                    readeck_timestamp = readeck_timestamp_to_epoch(bookmark["updated"])

                    # The Readeck sync endpoint doesn't reliably filter by timestamp,
                    # so we skip bookmarks that haven't actually changed since last sync.
                    if readeck_timestamp <= readeck_last_sync_epoch:
                        continue
                    
                    # Skip if this URL was already updated from Linkora and Linkora was newer.
                    if url in linkora_updated_urls:
                        linkora_link = linkora_updated_urls[url]
                        if linkora_link["eventTimestamp"] > readeck_timestamp:
                            continue
                    
                    link_tags = []
                    for label_name in bookmark.get("labels", []):
                        tag_id = state.get_tag_mapping_by_name(connection, label_name)
                        if tag_id is not None:
                            link_tags.append({"linkId": linkora_id, "tagId": tag_id})
                    
                    # Use the Linkora link from updates if available, otherwise use defaults
                    # for fields we don't sync (mediaType, idOfLinkedFolder).
                    linkora_link = next(
                        (link for link in linkora_updates["links"] if link["id"] == linkora_id),
                        None
                    )
                    
                    await linkora.update_link(
                        linkora_client,
                        config.linkora.url,
                        linkora_id,
                        bookmark["title"],
                        bookmark["url"],
                        bookmark.get("description", ""),
                        linkora_link["idOfLinkedFolder"] if linkora_link else linkora_folder_id,
                        bookmark.get("is_marked", False),
                        linkora_link["mediaType"] if linkora_link else "IMAGE",
                        link_tags,
                    )
                    logger.info(f"Updated Linkora link {linkora_id} from Readeck bookmark {readeck_uid}")
                else:
                    tag_ids = []
                    for label_name in bookmark.get("labels", []):
                        tag_id = state.get_tag_mapping_by_name(connection, label_name)
                        if tag_id is None:
                            tag_id = await linkora.create_tag(linkora_client, config.linkora.url, label_name)
                            state.add_tag_mapping(connection, tag_id, label_name)
                            logger.info(f"Created tag '{label_name}' in Linkora with ID {tag_id}")
                        tag_ids.append(tag_id)
                    
                    linkora_id = await linkora.create_link(
                        linkora_client,
                        config.linkora.url,
                        url,
                        bookmark["title"],
                        bookmark.get("description", ""),
                        linkora_folder_id,
                        bookmark.get("is_marked", False),
                        tag_ids,
                    )
                    state.add_mapping(connection, linkora_id, bookmark["id"], url)
                    logger.info(f"Created Linkora link {linkora_id} from Readeck bookmark {bookmark['id']}")
            except Exception as error:
                logger.warning(f"Failed to process Readeck bookmark {bookmark['id']}: {error}")
        
        # Phase 6: Finalize
        logger.info("Phase 6: Finalize")
        
        new_linkora_last_sync = str(int(time.time()))
        # Readeck expects the "Z" suffix, not "+00:00".
        new_readeck_last_sync = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        
        state.set_state(connection, "linkora_last_sync", new_linkora_last_sync)
        state.set_state(connection, "readeck_last_sync", new_readeck_last_sync)
        
        logger.info(f"Sync complete. Linkora last sync: {new_linkora_last_sync}, Readeck last sync: {new_readeck_last_sync}")
