# New Asset Workflow Notes

## Atlassian Assets Cloud API Endpoints
- Creating an asset uses `POST /jsm/assets/workspace/{workspaceId}/v1/object/create`.
- Model names can be fetched from `GET /jsm/assets/workspace/{workspaceId}/v1/objecttype/{objectTypeId}/objects`.
- Available statuses are retrieved via `GET /jsm/assets/workspace/{workspaceId}/v1/objecttype/{objectTypeId}/attributes`.

These endpoints were derived from Atlassian Assets Cloud API documentation. Attempts to access the documentation directly via curl returned HTTP 403 in this environment, so manual verification may be required.

## Interactive CLI Flow
1. Prompt user for asset serial number.
2. Fetch available model names via `list_models` (uses *GET objecttype/objects*).
3. Fetch available statuses via `list_statuses` (uses *GET objecttype/attributes*).
4. Ask whether the asset is for a remote user (`y`/`n`).
5. Submit details to `AssetManager.create_asset` which calls the *POST object/create* endpoint.
6. Offer to add another asset; repeat from step 1 if the user answers `y`.

## Dependency Versions
- `requests` is pinned at `>=2.31.0` while the latest release is `2.32.5`.
- `pytest` is installed at `8.4.1`; the latest release is `8.4.2`.

Update the dependencies if newer releases contain security or compatibility fixes.
