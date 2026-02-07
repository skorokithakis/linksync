import logging

import httpx

logger = logging.getLogger(__name__)


def _raise_for_status(response: httpx.Response) -> None:
    """Raise an error with the response body included for diagnostics."""
    if response.is_success:
        return
    raise httpx.HTTPStatusError(
        f"{response.status_code} {response.reason_phrase}: {response.text}",
        request=response.request,
        response=response,
    )


async def get_sync_changes(
    client: httpx.AsyncClient, base_url: str, since: str | None
) -> list[dict]:
    """Fetch bookmark sync changes from Readeck.

    Returns all changes if since is None, otherwise returns changes after the given timestamp.
    Each change has id, time (ISO 8601), and type (update or delete).
    """
    url = f"{base_url}/api/bookmarks/sync/"
    params = {"after": since} if since is not None else {}
    response = await client.get(url, params=params)
    _raise_for_status(response)
    return response.json()


async def get_bookmark(client: httpx.AsyncClient, base_url: str, uid: str) -> dict:
    """Fetch a single bookmark by UID from Readeck.

    Returns the full bookmark object including id, href, url, title, description,
    is_marked, is_archived, is_deleted, labels, and timestamps.
    """
    url = f"{base_url}/api/bookmarks/{uid}"
    response = await client.get(url)
    _raise_for_status(response)
    return response.json()


async def get_labels(client: httpx.AsyncClient, base_url: str) -> list[dict]:
    """Fetch all labels from Readeck.

    Returns a list of label objects, each containing at least name and count.
    Returns empty list if no labels exist.
    """
    url = f"{base_url}/api/bookmarks/labels"
    response = await client.get(url)
    _raise_for_status(response)
    return response.json()


async def create_bookmark(
    client: httpx.AsyncClient, base_url: str, url: str, title: str, labels: list[str]
) -> str:
    """Create a new bookmark in Readeck.

    Returns the UID of the created bookmark, extracted from the bookmark-id response header.
    Readeck returns 202 Accepted for async bookmark creation.
    """
    endpoint = f"{base_url}/api/bookmarks/"
    body = {"url": url, "title": title, "labels": labels}
    logger.debug(f"Creating bookmark: {url}")
    response = await client.post(endpoint, json=body)
    _raise_for_status(response)

    # Readeck returns 202 Accepted with the bookmark UID in the bookmark-id header.
    if response.status_code != 202:
        raise ValueError(
            f"Expected 202 Accepted, got {response.status_code} when creating bookmark for {url}"
        )

    bookmark_id = response.headers.get("bookmark-id")
    if not bookmark_id:
        raise ValueError(
            f"bookmark-id header missing from create_bookmark response for {url}, "
            f"headers: {dict(response.headers)}"
        )

    return bookmark_id


async def update_bookmark(
    client: httpx.AsyncClient, base_url: str, uid: str, fields: dict
) -> None:
    """Update an existing bookmark in Readeck.

    The fields dict can contain any subset of: title, description, labels, is_marked, is_archived.
    The labels field replaces all labels (full replace, not incremental).
    """
    url = f"{base_url}/api/bookmarks/{uid}"
    logger.debug(f"Updating bookmark {uid}: fields={list(fields.keys())}")
    response = await client.patch(url, json=fields)
    _raise_for_status(response)


async def delete_bookmark(
    client: httpx.AsyncClient, base_url: str, uid: str
) -> None:
    """Delete a bookmark from Readeck.

    Returns 204 No Content on success.
    """
    url = f"{base_url}/api/bookmarks/{uid}"
    logger.debug(f"Deleting bookmark {uid}")
    response = await client.delete(url)
    _raise_for_status(response)


async def rename_label(
    client: httpx.AsyncClient, base_url: str, old_name: str, new_name: str
) -> None:
    """Rename a label in Readeck.

    Updates all bookmarks with the old label name to use the new label name.
    """
    url = f"{base_url}/api/bookmarks/labels"
    params = {"name": old_name}
    body = {"name": new_name}
    logger.debug(f"Renaming label '{old_name}' -> '{new_name}'")
    response = await client.patch(url, params=params, json=body)
    _raise_for_status(response)
