import logging
import time

import httpx

# Correlation object included in all mutating requests to identify this client.
CORRELATION = {"id": "linksync", "clientName": "linksync"}


async def get_updates(client: httpx.AsyncClient, base_url: str, since_timestamp: int) -> dict:
    """Fetch all updates since the given timestamp.
    
    Returns AllTablesDTO containing links, folders, panels, panelFolders, tags, and linkTags.
    """
    response = await client.get(f"{base_url}/GET_UPDATES", params={"eventTimestamp": since_timestamp})
    response.raise_for_status()
    return response.json()


async def get_tombstones(client: httpx.AsyncClient, base_url: str, since_timestamp: int) -> list[dict]:
    """Fetch all tombstones (deletion records) since the given timestamp.
    
    Each tombstone contains deletedAt, operation, and payload fields.
    """
    response = await client.get(f"{base_url}/GET_TOMBSTONES", params={"eventTimestamp": since_timestamp})
    response.raise_for_status()
    return response.json()


async def get_tags(client: httpx.AsyncClient, base_url: str) -> list[dict]:
    """Fetch all tags from the server.
    
    Each tag contains id, name, and eventTimestamp.
    """
    response = await client.get(f"{base_url}/GET_TAGS")
    response.raise_for_status()
    return response.json()


async def get_root_folders(client: httpx.AsyncClient, base_url: str) -> list[dict]:
    """Fetch all root-level folders from the server.
    
    Each folder contains id, name, note, parentFolderId, isArchived, and eventTimestamp.
    """
    response = await client.get(f"{base_url}/GET_ROOT_FOLDERS")
    response.raise_for_status()
    return response.json()


async def create_folder(client: httpx.AsyncClient, base_url: str, name: str) -> int:
    """Create a new root-level folder and return its ID."""
    body = {
        "name": name,
        "note": "",
        "parentFolderId": None,
        "isArchived": False,
        "correlation": CORRELATION,
        "eventTimestamp": int(time.time()),
    }
    response = await client.post(f"{base_url}/CREATE_FOLDER", json=body)
    response.raise_for_status()
    return response.json()["id"]


async def create_link(
    client: httpx.AsyncClient,
    base_url: str,
    url: str,
    title: str,
    note: str,
    folder_id: int,
    marked_as_important: bool,
    tag_ids: list[int],
) -> int:
    """Create a new link and return its ID."""
    body = {
        "linkType": "FOLDER_LINK",
        "title": title,
        "url": url,
        "baseURL": "",
        "imgURL": "",
        "note": note,
        "idOfLinkedFolder": folder_id,
        "userAgent": None,
        "markedAsImportant": marked_as_important,
        "mediaType": "IMAGE",
        "correlation": CORRELATION,
        "eventTimestamp": int(time.time()),
        "tags": tag_ids,
        "forceRetrieveOGMetaInfo": True,
    }
    response = await client.post(f"{base_url}/CREATE_A_NEW_LINK", json=body)
    response.raise_for_status()
    return response.json()["id"]


async def update_link(
    client: httpx.AsyncClient,
    base_url: str,
    link_id: int,
    title: str,
    url: str,
    note: str,
    folder_id: int | None,
    marked_as_important: bool,
    media_type: str,
    link_tags: list[dict],
) -> None:
    """Update an existing link.
    
    Uses last-write-wins conflict resolution. If the server rejects the update
    because it already has newer data, logs a warning and returns without raising.
    """
    body = {
        "id": link_id,
        "linkType": "FOLDER_LINK",
        "title": title,
        "url": url,
        "baseURL": "",
        "imgURL": "",
        "note": note,
        "idOfLinkedFolder": folder_id,
        "userAgent": None,
        "markedAsImportant": marked_as_important,
        "mediaType": media_type,
        "correlation": CORRELATION,
        "linkTags": link_tags,
        "eventTimestamp": int(time.time()),
    }
    response = await client.post(f"{base_url}/UPDATE_LINK", json=body)
    
    # Handle LWW conflict: server already has newer data.
    if response.status_code == 500 and "This row already contains the latest data." in response.text:
        logging.warning(f"LWW conflict for link {link_id}: server has newer data, skipping update")
        return
    
    response.raise_for_status()


async def delete_link(client: httpx.AsyncClient, base_url: str, link_id: int) -> None:
    """Delete a link by ID."""
    body = {
        "id": link_id,
        "correlation": CORRELATION,
        "eventTimestamp": int(time.time()),
    }
    response = await client.post(f"{base_url}/DELETE_A_LINK", json=body)
    response.raise_for_status()


async def create_tag(client: httpx.AsyncClient, base_url: str, name: str) -> int:
    """Create a new tag and return its ID."""
    body = {
        "name": name,
        "eventTimestamp": int(time.time()),
        "correlation": CORRELATION,
    }
    response = await client.post(f"{base_url}/CREATE_TAG", json=body)
    response.raise_for_status()
    return response.json()["id"]


async def rename_tag(client: httpx.AsyncClient, base_url: str, tag_id: int, new_name: str) -> None:
    """Rename an existing tag."""
    body = {
        "id": tag_id,
        "newName": new_name,
        "eventTimestamp": int(time.time()),
        "correlation": CORRELATION,
    }
    response = await client.post(f"{base_url}/RENAME_TAG", json=body)
    response.raise_for_status()
