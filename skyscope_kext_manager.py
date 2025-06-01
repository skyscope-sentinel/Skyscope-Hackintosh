#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import os
import json
import fnmatch # For wildcard pattern matching
import shutil
import zipfile
import tempfile
from pathlib import Path # For easier path manipulations

USER_AGENT = "Skyscope-Kext-Downloader/1.0"

def download_kext_zip(kext_name: str, repo_path: str, asset_pattern: str, download_dir: str, fallback_asset_pattern: str = None) -> str | None:
    """
    Downloads a kext ZIP file from the latest GitHub release of a given repository.
    (Implementation from previous step, assumed to be correct)
    """
    print(f"\nProcessing {kext_name} from repository {repo_path}...")
    
    api_url = f"https://api.github.com/repos/{repo_path}/releases/latest"
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github.v3+json"}
    
    asset_download_url = None
    filename = None

    try:
        response = requests.get(api_url, headers=headers, timeout=15)
        response.raise_for_status() 
    except requests.exceptions.Timeout:
        print(f"  Error: Timeout while trying to fetch release info from {api_url}.")
        return None
    except requests.exceptions.RequestException as e:
        print(f"  Error: Failed to fetch release info from {api_url}. Exception: {e}")
        return None

    if response.status_code == 200:
        try:
            release_data = response.json()
        except json.JSONDecodeError:
            print(f"  Error: Could not decode JSON response from {api_url}.")
            return None
        
        assets = release_data.get('assets', [])
        if not assets:
            print(f"  Warning: No assets found in the latest release of {repo_path}.")
            return None

        for asset in assets:
            if fnmatch.fnmatch(asset['name'], asset_pattern):
                asset_download_url = asset.get('browser_download_url')
                filename = asset.get('name')
                print(f"  Found asset matching '{asset_pattern}': {filename}")
                break
        
        if not asset_download_url and fallback_asset_pattern:
            print(f"  Primary pattern '{asset_pattern}' failed. Trying fallback '{fallback_asset_pattern}'...")
            for asset in assets:
                if fnmatch.fnmatch(asset['name'], fallback_asset_pattern):
                    asset_download_url = asset.get('browser_download_url')
                    filename = asset.get('name')
                    print(f"  Found asset matching fallback '{fallback_asset_pattern}': {filename}")
                    break
        
        if not asset_download_url:
            print(f"  Warning: No asset found matching pattern(s) '{asset_pattern}'" + 
                  (f" or '{fallback_asset_pattern}'" if fallback_asset_pattern else "") +
                  f" in release {release_data.get('name', 'N/A')} for {repo_path}.")
            available_assets = [asset.get('name') for asset in assets]
            print(f"    Available assets: {', '.join(available_assets) if available_assets else 'None'}")
            return None
    else:
        print(f"  Error: Failed to get release info from {api_url}. Status code: {response.status_code}")
        print(f"    Response: {response.text[:200]}") 
        return None

    if not os.path.exists(download_dir):
        try:
            os.makedirs(download_dir, exist_ok=True)
            print(f"  Created download directory: {download_dir}")
        except OSError as e:
            print(f"  Error creating download directory {download_dir}: {e}")
            return None
            
    output_file_path = os.path.join(download_dir, filename)

    if os.path.exists(output_file_path) and os.path.getsize(output_file_path) > 0:
        print(f"  File '{filename}' already exists in '{download_dir}' and is not empty. Skipping download.")
        return output_file_path

    print(f"  Downloading '{filename}' from {asset_download_url}...")
    try:
        with requests.get(asset_download_url, stream=True, headers=headers, timeout=30) as r:
            r.raise_for_status()
            with open(output_file_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192): 
                    f.write(chunk)
        print(f"  Successfully downloaded '{filename}' to '{output_file_path}'.")
        return output_file_path
    except requests.exceptions.RequestException as e:
        print(f"  Error downloading file: {e}")
        if os.path.exists(output_file_path): 
            try: os.remove(output_file_path)
            except OSError as oe: print(f"    Error removing partial file '{output_file_path}': {oe}")
        return None
    except IOError as e:
        print(f"  Error writing file '{output_file_path}': {e}")
        if os.path.exists(output_file_path): 
             try: os.remove(output_file_path)
             except OSError as oe: print(f"    Error removing partial file '{output_file_path}': {oe}")
        return None

def find_kext_in_dir(search_dir: Path, kext_name_pattern: str, is_plugin_search: bool = False) -> Path | None:
    """
    Searches for a kext bundle directory within search_dir.
    If is_plugin_search, it looks for exact kext_name_pattern.
    Otherwise, it looks for a directory that starts with kext_name_pattern and ends with .kext.
    It prioritizes shallower results.
    """
    min_depth = float('inf')
    found_path = None

    for item_path in search_dir.rglob('*'): # rglob searches recursively
        if item_path.is_dir() and item_path.name.endswith(".kext"):
            if is_plugin_search:
                if item_path.name == kext_name_pattern:
                    depth = len(item_path.relative_to(search_dir).parts)
                    if depth < min_depth:
                        min_depth = depth
                        found_path = item_path
            # For primary kext, match start and .kext suffix
            elif item_path.name.startswith(kext_name_pattern) and not is_plugin_search:
                depth = len(item_path.relative_to(search_dir).parts)
                if depth < min_depth: # Prioritize top-level or less nested kexts
                    min_depth = depth
                    found_path = item_path
    return found_path


def stage_kext(kext_info: dict, zip_path: str, base_staging_dir: str) -> list:
    """
    Extracts and stages a kext and its specified plugins from a ZIP archive.

    Args:
        kext_info (dict): Info about the kext, including "name", "generic_kext_name", 
                          and optionally "plugins" (a list of plugin filenames).
        zip_path (str): Path to the downloaded kext ZIP file.
        base_staging_dir (str): Root directory for staging (e.g., "./Skyscope_EFI_Staging").

    Returns:
        list: A list of full paths to successfully staged .kext bundles.
    """
    if not os.path.exists(zip_path):
        print(f"  Error: Kext ZIP path does not exist: {zip_path}")
        return []

    kexts_staging_path = Path(base_staging_dir) / "OC" / "Kexts"
    try:
        os.makedirs(kexts_staging_path, exist_ok=True)
    except OSError as e:
        print(f"  Error creating kext staging directory {kexts_staging_path}: {e}")
        return []

    staged_kext_paths = []
    kext_name_prefix = kext_info.get("name", "UnknownKextName") # Used for finding the primary kext
    generic_kext_name = kext_info.get("generic_kext_name") # Target name in staging (e.g. Lilu.kext)
    
    print(f"  Staging {kext_name_prefix} from {zip_path} to {kexts_staging_path}")

    with tempfile.TemporaryDirectory() as tmpdir_str:
        tmpdir = Path(tmpdir_str)
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(tmpdir)
            print(f"    Extracted '{os.path.basename(zip_path)}' to temporary directory.")
        except zipfile.BadZipFile:
            print(f"    Error: Bad ZIP file: {zip_path}")
            return []
        except Exception as e:
            print(f"    Error extracting ZIP {zip_path}: {e}")
            return []

        # Stage the primary kext
        if generic_kext_name: # Only proceed if we have a target generic name
            found_primary_kext_path = find_kext_in_dir(tmpdir, kext_name_prefix)
            
            if found_primary_kext_path:
                target_kext_path = kexts_staging_path / generic_kext_name
                try:
                    if target_kext_path.exists():
                        print(f"      Removing existing target: {target_kext_path}")
                        shutil.rmtree(target_kext_path)
                    shutil.copytree(found_primary_kext_path, target_kext_path)
                    staged_kext_paths.append(str(target_kext_path))
                    print(f"      Successfully staged primary kext: {found_primary_kext_path.name} -> {target_kext_path.name}")
                except Exception as e:
                    print(f"      Error staging primary kext {found_primary_kext_path.name}: {e}")
            else:
                print(f"    Warning: Primary kext bundle starting with '{kext_name_prefix}' not found in {zip_path}.")
        else:
            print(f"    Warning: 'generic_kext_name' not provided for {kext_name_prefix}, cannot stage primary kext.")

        # Stage plugins if any are specified
        plugins_to_stage = kext_info.get("plugins", [])
        if plugins_to_stage:
            print(f"    Attempting to stage plugins: {', '.join(plugins_to_stage)}")
            for plugin_filename in plugins_to_stage: # e.g., "SMCProcessor.kext"
                found_plugin_path = find_kext_in_dir(tmpdir, plugin_filename, is_plugin_search=True)
                if found_plugin_path:
                    target_plugin_path = kexts_staging_path / plugin_filename
                    try:
                        if target_plugin_path.exists():
                            print(f"      Removing existing target: {target_plugin_path}")
                            shutil.rmtree(target_plugin_path)
                        shutil.copytree(found_plugin_path, target_plugin_path)
                        staged_kext_paths.append(str(target_plugin_path))
                        print(f"      Successfully staged plugin: {found_plugin_path.name} -> {target_plugin_path.name}")
                    except Exception as e:
                        print(f"      Error staging plugin {found_plugin_path.name}: {e}")
                else:
                    print(f"    Warning: Plugin '{plugin_filename}' not found in {zip_path}.")
                    
    return staged_kext_paths


if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    kext_download_dir = os.path.join(script_dir, "downloads", "kext_zips")
    base_staging_dir_test = os.path.join(script_dir, "test_EFI_staging") # Test staging directory

    print(f"Kexts will be downloaded to: {kext_download_dir}")
    print(f"Staging base directory: {base_staging_dir_test}")

    # Ensure staging directory exists for testing
    if os.path.exists(base_staging_dir_test):
        print(f"Cleaning up existing test staging directory: {base_staging_dir_test}")
        shutil.rmtree(base_staging_dir_test)
    os.makedirs(base_staging_dir_test, exist_ok=True)
    
    kexts_to_test = [
        {
            "name": "Lilu", "repo": "acidanthera/Lilu", 
            "pattern": "*RELEASE.zip", "generic_kext_name": "Lilu.kext"
        },
        {
            "name": "VirtualSMC", "repo": "acidanthera/VirtualSMC", 
            "pattern": "*RELEASE.zip", "generic_kext_name": "VirtualSMC.kext",
            "plugins": ["SMCProcessor.kext", "SMCSuperIO.kext", "SMCBatteryManager.kext"] # SMCBatteryManager might not be in all zips
        },
        {
            "name": "RealtekRTL8111", "repo": "Mieze/RTL8111_driver_for_OS_X",
            "pattern": "*RELEASE.zip", "fallback": "*.zip", "generic_kext_name": "RealtekRTL8111.kext"
        }
    ]

    all_staged_files = []
    for kext_data in kexts_to_test:
        downloaded_path = download_kext_zip(
            kext_name=kext_data["name"],
            repo_path=kext_data["repo"],
            asset_pattern=kext_data["pattern"],
            download_dir=kext_download_dir,
            fallback_asset_pattern=kext_data.get("fallback")
        )
        if downloaded_path:
            print(f"  {kext_data['name']} downloaded/verified at: {downloaded_path}")
            staged_paths = stage_kext(kext_data, downloaded_path, base_staging_dir_test)
            if staged_paths:
                all_staged_files.extend(staged_paths)
                print(f"  Successfully staged for {kext_data['name']}: {staged_paths}")
            else:
                print(f"  Staging failed or no kexts found for {kext_data['name']}.")
        else:
            print(f"  Failed to download {kext_data['name']}.")

    print("\n--- Summary of Staged Kexts ---")
    if all_staged_files:
        for p in all_staged_files:
            print(f"  - {p}")
    else:
        print("  No kexts were staged.")

    print(f"\nCheck the '{base_staging_dir_test}/OC/Kexts' directory for staged kexts.")
