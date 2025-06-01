#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import cpuinfo
import platform
import json 
import plistlib 
import os 
import re 

# Assuming skyscope_config_parts.py is in the same directory
from skyscope_config_parts import generate_cpu_config_parts, generate_gpu_config_parts, \
                                  generate_audio_config_parts, generate_ethernet_config_parts

def get_cpu_details():
    details = {}
    try:
        info = cpuinfo.get_cpu_info()
        details['raw_info'] = info 
        details['brand_raw'] = info.get('brand_raw', 'N/A')
        details['hz_advertised'] = info.get('hz_advertised_friendly', 'N/A')
        details['hz_actual'] = info.get('hz_actual_friendly', 'N/A')
        details['arch_string_raw'] = info.get('arch_string_raw', 'N/A')
        details['vendor_id_raw'] = info.get('vendor_id_raw', 'N/A')
        details['logical_cores'] = info.get('count', 'N/A')
        details['physical_cores'] = info.get('cores', "N/A (py-cpuinfo may not provide this consistently)")
        details['flags'] = info.get('flags', [])
    except Exception as e:
        details['error'] = str(e)
    return details

def get_gpu_details():
    gpu_list = []
    try:
        import wmi 
    except ImportError:
        print("  WMI module not found. GPU detection via WMI is not available (likely non-Windows OS).")
        return gpu_list 

    try:
        c = wmi.WMI()
        video_controllers = c.Win32_VideoController()
        if not video_controllers:
            print("  No video controllers found via WMI.")
            return gpu_list

        for controller in video_controllers:
            gpu_info = {
                "Name": controller.Name, "Caption": controller.Caption,
                "AdapterCompatibility": controller.AdapterCompatibility, "VideoProcessor": controller.VideoProcessor,
                "DriverVersion": controller.DriverVersion, "AdapterRAM_MB": None,
                "PNPDeviceID": controller.PNPDeviceID, "Status": controller.Status,
                "Availability": controller.Availability, "ConfigManagerErrorCode": controller.ConfigManagerErrorCode,
                "VendorID": None, "DeviceID": None,
                "SubsystemVendorID": None, "SubsystemID": None
            }
            if controller.AdapterRAM:
                gpu_info["AdapterRAM_MB"] = int(controller.AdapterRAM / (1024**2))
            pnp_id = controller.PNPDeviceID
            if pnp_id:
                vid_match = re.search(r"VEN_([0-9A-F]{4})", pnp_id, re.IGNORECASE)
                if vid_match: gpu_info["VendorID"] = vid_match.group(1)
                did_match = re.search(r"DEV_([0-9A-F]{4})", pnp_id, re.IGNORECASE)
                if did_match: gpu_info["DeviceID"] = did_match.group(1)
                subsys_match = re.search(r"SUBSYS_([0-9A-F]{4})([0-9A-F]{4})", pnp_id, re.IGNORECASE)
                if subsys_match:
                    gpu_info["SubsystemVendorID"] = subsys_match.group(1) 
                    gpu_info["SubsystemID"] = subsys_match.group(2)     
            gpu_list.append(gpu_info)
    except Exception as e:
        print(f"  Error querying WMI for Win32_VideoController: {e}")
        try:
            if isinstance(e, wmi.x_wmi): 
                 print(f"  WMI Error Details: {e.com_error}")
        except Exception: pass
    return gpu_list

def get_audio_details():
    audio_devices_list = []
    try:
        import wmi 
        c = wmi.WMI()
        sound_devices = c.Win32_SoundDevice()
        if not sound_devices:
            print("  No sound devices found via WMI or WMI access limited.")
            return audio_devices_list
        for device in sound_devices:
            device_info = {
                "Name": device.ProductName, "Manufacturer": device.Manufacturer,
                "PNPDeviceID": device.PNPDeviceID, "Status": device.Status,
                "VendorID": None, "DeviceID": None,
                "SubsystemVendorID": None, "SubsystemID": None
            }
            pnp_id = device.PNPDeviceID
            if pnp_id:
                ven_match = re.search(r"VEN_([0-9A-F]{4})", pnp_id, re.IGNORECASE)
                if ven_match: device_info["VendorID"] = ven_match.group(1)
                dev_match = re.search(r"DEV_([0-9A-F]{4})", pnp_id, re.IGNORECASE)
                if dev_match: device_info["DeviceID"] = dev_match.group(1)
                subsys_match = re.search(r"SUBSYS_([0-9A-F]{4})([0-9A-F]{4})", pnp_id, re.IGNORECASE)
                if subsys_match:
                    device_info["SubsystemVendorID"] = subsys_match.group(1)
                    device_info["SubsystemID"] = subsys_match.group(2)
            audio_devices_list.append(device_info)
    except ImportError:
        print("  WMI module not found. Audio device detection via WMI is not available (likely non-Windows OS).")
    except Exception as e:
        print(f"  Error querying WMI for Win32_SoundDevice: {e}")
        try:
            if isinstance(e, wmi.x_wmi): 
                 print(f"  WMI Error Details: {e.com_error}")
        except Exception: pass
    return audio_devices_list

def get_ethernet_details():
    ethernet_devices_list = []
    wmi_imported = False
    try:
        import wmi
        wmi_imported = True
    except ImportError:
        print("  WMI module not found. Ethernet device detection via WMI is not available (likely non-Windows OS).")
        return ethernet_devices_list

    if wmi_imported:
        try:
            c = wmi.WMI()
            query = "SELECT * FROM Win32_NetworkAdapter WHERE PhysicalAdapter = True AND PNPDeviceID IS NOT NULL AND (AdapterTypeID = 0 OR Name LIKE '%Ethernet%' OR ServiceName LIKE '%eth%')"
            network_adapters = c.query(query)

            if not network_adapters:
                print("  No suitable physical Ethernet controllers found via WMI.")
                return ethernet_devices_list
            
            for adapter in network_adapters:
                if not adapter.PNPDeviceID or "PCI\\" not in adapter.PNPDeviceID.upper():
                    continue # Skip non-PCI devices

                device_info = {
                    "Name": adapter.Name, "ProductName": adapter.ProductName,
                    "PNPDeviceID": adapter.PNPDeviceID, "Manufacturer": adapter.Manufacturer,
                    "MACAddress": adapter.MACAddress, "Speed": adapter.Speed,
                    "VendorID": None, "DeviceID": None
                }
                pnp_id = adapter.PNPDeviceID
                ven_match = re.search(r"VEN_([0-9A-F]{4})", pnp_id, re.IGNORECASE)
                if ven_match: device_info["VendorID"] = ven_match.group(1).upper()
                dev_match = re.search(r"DEV_([0-9A-F]{4})", pnp_id, re.IGNORECASE)
                if dev_match: device_info["DeviceID"] = dev_match.group(1).upper()
                
                if device_info["VendorID"] and device_info["DeviceID"]:
                    ethernet_devices_list.append(device_info)
        
        except wmi.x_wmi as wmi_exception:
            print(f"  WMI query error for Win32_NetworkAdapter: {wmi_exception}")
            print(f"  WMI Error Details: {getattr(wmi_exception, 'com_error', 'N/A')}")
        except Exception as e:
            print(f"  Error querying WMI for Win32_NetworkAdapter: {e}")
    
    return ethernet_devices_list

def merge_config_dicts(main_dict, new_dict):
    for key, new_value in new_dict.items():
        if key not in main_dict:
            main_dict[key] = new_value
        else:
            # Key exists in both, merge based on type
            main_value = main_dict[key]
            if isinstance(main_value, dict) and isinstance(new_value, dict):
                # Special handling for NVRAM boot-args
                guid_key = "7C436110-AB2A-4BBB-A880-FE41995C9F82"
                if key == "NVRAM" and "Add" in main_value and "Add" in new_value and \
                   guid_key in main_value["Add"] and guid_key in new_value["Add"]:
                    
                    main_boot_args_container = main_value["Add"][guid_key]
                    new_boot_args_container = new_value["Add"][guid_key]

                    main_boot_args_str = main_boot_args_container.get("boot-args", "")
                    new_boot_args_str = new_boot_args_container.get("boot-args", "")
                    
                    combined_args_set = set(main_boot_args_str.split())
                    combined_args_set.update(new_boot_args_str.split())
                    
                    final_boot_args = " ".join(sorted(list(filter(None, combined_args_set))))
                    
                    # Update the main_dict directly
                    if final_boot_args:
                        main_dict[key]["Add"][guid_key]["boot-args"] = final_boot_args
                    elif "boot-args" in main_dict[key]["Add"][guid_key]:
                         del main_dict[key]["Add"][guid_key]["boot-args"]
                    
                    # Merge other keys within the GUID dict if any
                    for sub_key, sub_val in new_boot_args_container.items():
                        if sub_key != "boot-args":
                            main_dict[key]["Add"][guid_key][sub_key] = sub_val
                else: # Generic dictionary merge
                    merge_config_dicts(main_value, new_value) # Recursive call for nested dicts

            elif isinstance(main_value, list) and isinstance(new_value, list):
                # Specifically for Kernel/Add list, ensure uniqueness of kexts by BundlePath
                if key == "Add" and main_dict.get("Kernel") is main_value: # Heuristic: check if parent is Kernel
                    existing_bundle_paths = {kext.get("BundlePath") for kext in main_value}
                    for kext_to_add in new_value:
                        if kext_to_add.get("BundlePath") not in existing_bundle_paths:
                            main_value.append(kext_to_add)
                            existing_bundle_paths.add(kext_to_add.get("BundlePath"))
                else: # Default list behavior: concatenate
                    main_dict[key] = main_value + new_value
            else: 
                main_dict[key] = new_value # Overwrite if types mismatch or not dict/list
    return main_dict


if __name__ == "__main__":
    final_opencore_config = {}

    print("Detecting CPU information...")
    cpu_details_result = get_cpu_details()
    if 'error' in cpu_details_result:
        print(f"Error collecting CPU details: {cpu_details_result['error']}")
    else:
        print("\n--- Detected CPU Information ---")
        print(f"  Brand:          {cpu_details_result.get('brand_raw')}")
        if 'raw_info' in cpu_details_result:
            print("\n--- Generating CPU Config Parts ---")
            target_smbios = "iMac20,2" 
            cpu_config_parts = generate_cpu_config_parts(cpu_details_result['raw_info'], target_smbios=target_smbios)
            final_opencore_config = merge_config_dicts(final_opencore_config, cpu_config_parts)
        else:
            print("  Could not generate CPU config parts as raw_info was missing.")

    print("\n--- Detecting GPU Information ---")
    gpu_details_list = get_gpu_details()
    if gpu_details_list:
        for i, gpu in enumerate(gpu_details_list):
            print(f"\nGPU {i+1}: Name: {gpu.get('Name')}, VEN_{gpu.get('VendorID')}, DEV_{gpu.get('DeviceID')}")
    else:
        print("  No GPU details found or WMI error.")

    if 'raw_info' in cpu_details_result: 
        print("\n--- Generating GPU Config Parts ---")
        gpu_config_parts = generate_gpu_config_parts(gpu_details_list, cpu_details_result['raw_info'])
        final_opencore_config = merge_config_dicts(final_opencore_config, gpu_config_parts)
    else:
        print("  Skipping GPU config parts generation as CPU raw_info is missing.")
    
    print("\n--- Detecting Audio Device Information ---")
    audio_details_list = get_audio_details()
    if audio_details_list:
        print("  Summary of Detected Audio Devices:")
        for i, audio_dev in enumerate(audio_details_list):
            print(f"  Audio Device {i+1}: Name: {audio_dev.get('Name')}, VEN_{audio_dev.get('VendorID')}, DEV_{audio_dev.get('DeviceID')}")
    else:
        print("  No Audio details found or WMI error.")

    print("\n--- Generating Audio Config Parts ---")
    audio_config_parts = generate_audio_config_parts(audio_details_list)
    final_opencore_config = merge_config_dicts(final_opencore_config, audio_config_parts)

    print("\n--- Detecting Ethernet Controller Information ---")
    ethernet_details_list = get_ethernet_details()
    if ethernet_details_list:
        print("  Summary of Detected Ethernet Controllers:")
        for i, eth_dev in enumerate(ethernet_details_list):
            print(f"  Ethernet {i+1}: Name: {eth_dev.get('ProductName', eth_dev.get('Name'))}, VEN_{eth_dev.get('VendorID')}, DEV_{eth_dev.get('DeviceID')}")
    else:
        print("  No Ethernet details found or WMI error.")

    print("\n--- Generating Ethernet Config Parts ---")
    ethernet_config_parts = generate_ethernet_config_parts(ethernet_details_list)
    final_opencore_config = merge_config_dicts(final_opencore_config, ethernet_config_parts)

    # Ensure essential base kexts like Lilu and VirtualSMC are present if any other kexts were added
    kernel_add_list = final_opencore_config.setdefault("Kernel", {}).setdefault("Add", [])
    current_bundle_paths = {kext.get("BundlePath") for kext in kernel_add_list}

    essential_kexts_order = ["Lilu.kext", "VirtualSMC.kext"] # Ensure Lilu is first, then VirtualSMC
    
    # Add essential kexts if not present, maintaining a specific order for Lilu and VirtualSMC
    temp_kext_list_for_sorting = list(kernel_add_list) # Start with existing kexts

    from skyscope_config_parts import KEXT_INFO_DB, COMMON_KEXT_PROPERTIES # Re-import for this block
    
    for kext_bundle_path in reversed(essential_kexts_order): # Add in reverse to make them appear at the top when prepending
        if kext_bundle_path not in current_bundle_paths:
            kext_name = os.path.splitext(kext_bundle_path)[0] # e.g. "Lilu" from "Lilu.kext"
            if kext_name in KEXT_INFO_DB:
                entry = KEXT_INFO_DB[kext_name].copy()
                entry.update(COMMON_KEXT_PROPERTIES)
                # Prepend to ensure Lilu is first, then VirtualSMC
                temp_kext_list_for_sorting.insert(0, entry) 
                current_bundle_paths.add(kext_bundle_path) 
                print(f"    Ensured {kext_bundle_path} is added to Kernel/Add.")
            else:
                print(f"    Warning: Kext info for essential kext '{kext_name}' not found in KEXT_INFO_DB.")
    
    # Re-assign the potentially modified list back
    final_opencore_config["Kernel"]["Add"] = temp_kext_list_for_sorting


    if final_opencore_config:
        print("\n--- Final Merged OpenCore Configuration (CPU + GPU + Audio + Ethernet) ---")
        try:
            plist_xml_bytes = plistlib.dumps(final_opencore_config, sort_keys=True)
            plist_xml_string = plist_xml_bytes.decode('utf-8')
            print("\nGenerated Plist XML (Merged Hardware Parts):\n")
            print(plist_xml_string)

            output_filename = "config_generated.plist"
            try:
                with open(output_filename, "wb") as fp:
                    plistlib.dump(final_opencore_config, fp, sort_keys=True)
                print(f"\nSuccessfully saved merged plist to: {output_filename}")
                if os.path.exists(output_filename):
                    print(f"File '{output_filename}' confirmed to exist.")
                else:
                    print(f"File '{output_filename}' NOT found after save attempt.")
            except Exception as e:
                print(f"\nError saving merged plist to file: {e}")
        except Exception as e:
            print(f"\nError serializing final dictionary to plist XML: {e}")
    else:
        print("\nNo OpenCore configuration was generated.")
