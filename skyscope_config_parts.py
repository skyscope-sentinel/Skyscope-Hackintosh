#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import base64
import os # For os.urandom
import plistlib # For plistlib.Data and eventually dumping to file
import json   # For pretty printing dict during testing

# --- Kext Information Database and Common Properties ---
KEXT_INFO_DB = {
    "Lilu": {
        "BundlePath": "Lilu.kext",
        "Comment": "Core kext patching library",
        "ExecutablePath": "Contents/MacOS/Lilu",
    },
    "VirtualSMC": {
        "BundlePath": "VirtualSMC.kext",
        "Comment": "Advanced SMC emulator",
        "ExecutablePath": "Contents/MacOS/VirtualSMC",
    },
    "WhateverGreen": {
        "BundlePath": "WhateverGreen.kext",
        "Comment": "Graphics card patching (Intel, AMD, NVIDIA)",
        "ExecutablePath": "Contents/MacOS/WhateverGreen",
    },
    "AppleALC": {
        "BundlePath": "AppleALC.kext",
        "Comment": "Audio patching for unsupported codecs",
        "ExecutablePath": "Contents/MacOS/AppleALC",
    },
    "RealtekRTL8111": { # For RTL8111/8168
        "BundlePath": "RealtekRTL8111.kext",
        "Comment": "Realtek Gigabit Ethernet (RTL8111/8168)",
        "ExecutablePath": "Contents/MacOS/RealtekRTL8111",
    },
    "LucyRTL8125Ethernet": { # For RTL8125 (2.5GbE)
        "BundlePath": "LucyRTL8125Ethernet.kext",
        "Comment": "Realtek 2.5Gb Ethernet (RTL8125)",
        "ExecutablePath": "Contents/MacOS/LucyRTL8125Ethernet",
    },
    "IntelMausi": { # Common for Intel Ethernet
        "BundlePath": "IntelMausi.kext",
        "Comment": "Intel Ethernet LAN kext (most common Intel NICs)",
        "ExecutablePath": "Contents/MacOS/IntelMausi",
    },
    # Add other kexts here as needed, e.g., USBMap, NVMeFix, SMC plugins
    "SMCProcessor": {
        "BundlePath": "SMCProcessor.kext",
        "Comment": "VirtualSMC Plugin for CPU temperature monitoring",
        "ExecutablePath": "Contents/MacOS/SMCProcessor",
    },
    "SMCSuperIO": {
        "BundlePath": "SMCSuperIO.kext",
        "Comment": "VirtualSMC Plugin for fan speed monitoring",
        "ExecutablePath": "Contents/MacOS/SMCSuperIO",
    },
    "NVMeFix": {
         "BundlePath": "NVMeFix.kext",
         "Comment": "NVMe power management and compatibility fixes",
         "ExecutablePath": "Contents/MacOS/NVMeFix",
    }
}

COMMON_KEXT_PROPERTIES = {
    "Arch": "Any",
    "Enabled": True,
    "MaxKernel": "",
    "MinKernel": "",
    "PlistPath": "Contents/Info.plist"
}
# --- End Kext Info ---


def generate_cpu_config_parts(cpu_info_dict: dict, target_smbios: str = "iMac20,2") -> dict:
    """
    Generates CPU-relevant sections of an OpenCore config.plist dictionary.
    Input cpu_info_dict is expected to be from py-cpuinfo.
    """
    if not isinstance(cpu_info_dict, dict):
        print("Error: cpu_info_dict must be a dictionary.")
        return {} 

    config_dict = {
        "ACPI": {"Add": []},
        "Kernel": {
            "Add": [], # Initialize Kernel/Add for CPU related kexts like SMC plugins
            "Quirks": {},
            "Emulate": {}
        },
        "PlatformInfo": {
            "Generic": {}
        }
    }

    config_dict["PlatformInfo"]["Generic"]["SystemProductName"] = target_smbios
    config_dict["PlatformInfo"]["Generic"]["ProcessorType"] = 0 
    
    try:
        rom_bytes = os.urandom(6)
    except NotImplementedError: 
        import random
        rom_bytes = bytes([random.randint(0, 255) for _ in range(6)])
        
    config_dict["PlatformInfo"]["Generic"]["ROM"] = rom_bytes 
    config_dict["PlatformInfo"]["Generic"]["SystemSerialNumber"] = "NOT_YET_GENERATED_SERIAL"
    config_dict["PlatformInfo"]["Generic"]["MLB"] = "NOT_YET_GENERATED_MLB"
    config_dict["PlatformInfo"]["Generic"]["SystemUUID"] = "NOT_YET_GENERATED_UUID"
    config_dict["PlatformInfo"]["Generic"]["SpoofVendor"] = True 

    cpu_brand_raw = cpu_info_dict.get('brand_raw', "").lower()
    is_modern_intel_desktop = False
    if "intel" in cpu_brand_raw and ("core" in cpu_brand_raw or "pentium" in cpu_brand_raw or "celeron" in cpu_brand_raw):
        if any(gen_tag in cpu_brand_raw for gen_tag in ["8th gen", "9th gen", "10th gen", "11th gen", "12th gen", "13th gen", "14th gen"]) or \
           any(cpu_brand_raw.startswith(prefix) for prefix in ["intel(r) core(tm) i3-", "intel(r) core(tm) i5-", "intel(r) core(tm) i7-", "intel(r) core(tm) i9-"]):
            is_modern_intel_desktop = True 

    if is_modern_intel_desktop:
        print(f"    Detected modern Intel desktop CPU ({cpu_info_dict.get('brand_raw', 'N/A')}), adding common ACPI SSDTs.")
        config_dict["ACPI"]["Add"].extend([
            {"Comment": "SSDT-PLUG-ALT - CPU Power Management", "Enabled": True, "Path": "SSDT-PLUG-ALT.aml"},
            {"Comment": "SSDT-EC-USBX-DESKTOP - Embedded Controller and USBX Fix", "Enabled": True, "Path": "SSDT-EC-USBX-DESKTOP.aml"},
            {"Comment": "SSDT-AWAC-DISABLE - Disable AWAC, use system RTC", "Enabled": True, "Path": "SSDT-AWAC-DISABLE.aml"},
            {"Comment": "SSDT-RHUB - USB Reset", "Enabled": True, "Path": "SSDT-RHUB.aml"}
        ])
        # Add VirtualSMC plugins for modern Intel desktops
        for kext_name in ["SMCProcessor", "SMCSuperIO"]: # NVMeFix is more general
            if kext_name in KEXT_INFO_DB:
                entry = KEXT_INFO_DB[kext_name].copy()
                entry.update(COMMON_KEXT_PROPERTIES)
                config_dict["Kernel"]["Add"].append(entry)
    else:
        print(f"    CPU ({cpu_info_dict.get('brand_raw', 'N/A')}) not matching modern Intel desktop criteria for common SSDTs/SMC Kexts. ACPI/Kernel Add for CPU is minimal.")

    # Add NVMeFix generally if NVMe might be present (most modern systems)
    if "NVMeFix" in KEXT_INFO_DB:
        entry = KEXT_INFO_DB["NVMeFix"].copy()
        entry.update(COMMON_KEXT_PROPERTIES)
        config_dict["Kernel"]["Add"].append(entry)

    config_dict["Kernel"]["Quirks"]["ProvideCurrentCpuInfo"] = True
    config_dict["Kernel"]["Quirks"]["AppleXcpmCfgLock"] = True  
    config_dict["Kernel"]["Quirks"]["AppleCpuPmCfgLock"] = False 
    config_dict["Kernel"]["Quirks"]["DummyPowerManagement"] = False 

    config_dict["Kernel"]["Emulate"]["Cpuid1Data"] = b'' 
    config_dict["Kernel"]["Emulate"]["Cpuid1Mask"] = b''

    return config_dict

def generate_gpu_config_parts(gpu_details_list: list, cpu_info_dict: dict) -> dict:
    if not isinstance(gpu_details_list, list): gpu_details_list = []
    if not isinstance(cpu_info_dict, dict): cpu_info_dict = {}

    final_gpu_parts = {
        "DeviceProperties": {"Add": {}},
        "NVRAM": {"Add": {"7C436110-AB2A-4BBB-A880-FE41995C9F82": {"boot-args": ""}}},
        "Kernel": {"Add": []} # For GPU related kexts like WhateverGreen
    }
    device_properties_add = {}
    boot_args_to_add = []
    kernel_add_gpu = []
    added_kexts_gpu_set = set()
    has_active_igpu = False 

    cpu_brand_raw = cpu_info_dict.get('brand_raw', "").lower()
    
    intel_gt1_desktop_dids = [
        "4680", "4690", "a780", "46a0", 
        "4682", "4692", "a782", "a788", "46a2",
        "468b", "469b", "a78b"
    ] 

    print("\n--- Analyzing GPU details for config parts ---")
    is_any_gpu_configured = False
    for gpu in gpu_details_list:
        vid = gpu.get("VendorID", "").lower()
        did = gpu.get("DeviceID", "").lower()
        name = gpu.get("Name", "Unknown GPU")

        if vid == "8086": 
            print(f"  Processing Intel GPU: {name} (DID: {did})")
            is_target_cpu_gen = any(gen_tag in cpu_brand_raw for gen_tag in ["12th gen intel core", "13th gen intel core", "14th gen intel core"])
            if is_target_cpu_gen and did in intel_gt1_desktop_dids:
                pci_path_igpu = "PciRoot(0x0)/Pci(0x2,0x0)" 
                igpu_props = {
                    "AAPL,ig-platform-id": bytes.fromhex("0B00A000"), 
                    "device-id": int(did, 16).to_bytes(2, 'little') + b'\x00\x00', 
                    "framebuffer-patch-enable": bytes.fromhex("01000000"), 
                    "framebuffer-stolenmem": bytes.fromhex("00000004")    
                }
                device_properties_add[pci_path_igpu] = igpu_props
                boot_args_to_add.append("agdpmod=pikera") 
                has_active_igpu = True
                is_any_gpu_configured = True
                print(f"    Configured Intel iGPU: {name} (VID:{vid}, DID:{did}) with AAPL,ig-platform-id 0B00A000.")

        elif vid == "10de": 
            print(f"  Processing NVIDIA GPU: {name} (DID: {did})")
            is_any_gpu_configured = True # Mark that we processed a dGPU
            if did == "13c2": 
                print(f"    Detected NVIDIA GTX 970: {name}. This GPU is not supported by modern macOS.")
                if has_active_igpu:
                    boot_args_to_add.append("-wegnoegpu") 
                    print("      -wegnoegpu added to boot-args to prioritize iGPU over unsupported NVIDIA dGPU.")
            else:
                print(f"    Detected other NVIDIA GPU: {name} (VID:{vid}, DID:{did}). Modern NVIDIA dGPUs are generally unsupported.")
                if has_active_igpu: 
                    boot_args_to_add.append("-wegnoegpu")
                    print("      -wegnoegpu added to boot-args to prioritize iGPU over unsupported NVIDIA dGPU.")
        
        elif vid == "1002": 
            print(f"  Processing AMD GPU: {name} (DID: {did})")
            boot_args_to_add.append("agdpmod=pikera")
            is_any_gpu_configured = True
            print(f"    Added 'agdpmod=pikera' for AMD GPU: {name}. Further model-specific properties may be needed.")

    if is_any_gpu_configured and "WhateverGreen" not in added_kexts_gpu_set:
        if "WhateverGreen" in KEXT_INFO_DB:
            entry = KEXT_INFO_DB["WhateverGreen"].copy()
            entry.update(COMMON_KEXT_PROPERTIES)
            kernel_add_gpu.append(entry)
            added_kexts_gpu_set.add("WhateverGreen")
            print("    Added WhateverGreen.kext for GPU configuration.")

    final_gpu_parts["DeviceProperties"]["Add"] = device_properties_add
    if kernel_add_gpu:
        final_gpu_parts["Kernel"]["Add"] = kernel_add_gpu
    if boot_args_to_add:
        unique_boot_args = sorted(list(set(boot_args_to_add))) 
        final_gpu_parts["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"]["boot-args"] = " ".join(unique_boot_args)
    
    return final_gpu_parts

def generate_audio_config_parts(audio_devices_list: list) -> dict:
    if not isinstance(audio_devices_list, list): audio_devices_list = []

    final_audio_parts = {
        "DeviceProperties": {"Add": {}},
        "NVRAM": {"Add": {"7C436110-AB2A-4BBB-A880-FE41995C9F82": {"boot-args": ""}}},
        "Kernel": {"Add": []} # For AppleALC
    }
    device_properties_add = {}
    boot_args_to_add_list = [] 
    kernel_add_audio = []
    added_kexts_audio_set = set()
    found_onboard_audio = False
    
    target_codec_vid = "10EC" 
    chosen_layout_id = 11 
    audio_pci_path = "PciRoot(0x0)/Pci(0x1F,0x3)" 

    print("\n--- Analyzing Audio details for config parts ---")
    for device in audio_devices_list:
        vendor_id = device.get("VendorID", "")
        name = device.get("Name", "").lower()
        pnp_id = device.get("PNPDeviceID", "").upper()

        if "HDAUDIO" in pnp_id and vendor_id and vendor_id.upper() == target_codec_vid:
            print(f"    Identified likely onboard Realtek HDAudio controller: {device.get('Name')} (VID:{vendor_id})")
            print(f"      PNP ID suggesting Realtek: {pnp_id}")
            audio_props = {"layout-id": chosen_layout_id.to_bytes(4, byteorder='little')}
            if audio_pci_path not in device_properties_add:
                device_properties_add[audio_pci_path] = audio_props
                boot_args_to_add_list.append(f"alcid={chosen_layout_id}")
                if "AppleALC" not in added_kexts_audio_set and "AppleALC" in KEXT_INFO_DB:
                    entry = KEXT_INFO_DB["AppleALC"].copy()
                    entry.update(COMMON_KEXT_PROPERTIES)
                    kernel_add_audio.append(entry)
                    added_kexts_audio_set.add("AppleALC")
                found_onboard_audio = True
                break 
            else:
                print(f"    Skipping additional Realtek device on path {audio_pci_path} as it's already configured.")

    if device_properties_add:
        final_audio_parts["DeviceProperties"]["Add"] = device_properties_add
    if kernel_add_audio:
        final_audio_parts["Kernel"]["Add"] = kernel_add_audio
    if boot_args_to_add_list: 
        unique_boot_args = " ".join(sorted(list(set(boot_args_to_add_list))))
        final_audio_parts["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"]["boot-args"] = unique_boot_args
        
    if found_onboard_audio:
        print(f"    Audio config parts: Added AppleALC.kext, layout-id {chosen_layout_id} for {audio_pci_path} and 'alcid={chosen_layout_id}' to boot-args proposal.")
    else:
        print("    No specific onboard Realtek audio device found for AppleALC configuration.")
        # Remove empty NVRAM structure if no boot-args were added
        if not final_audio_parts["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"]["boot-args"]:
            del final_audio_parts["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"]
            if not final_audio_parts["NVRAM"]["Add"]:
                del final_audio_parts["NVRAM"]["Add"]
            if not final_audio_parts["NVRAM"]:
                del final_audio_parts["NVRAM"]


    return final_audio_parts

def generate_ethernet_config_parts(ethernet_devices_list: list) -> dict:
    if not isinstance(ethernet_devices_list, list):
        ethernet_devices_list = []

    kernel_add_entries = []
    added_kexts_set = set() 

    print("\n--- Analyzing Ethernet details for config parts ---")
    for device in ethernet_devices_list:
        vendor_id = device.get("VendorID", "").upper()
        device_id = device.get("DeviceID", "").upper()
        kext_name_to_use = None
        # Use ProductName if available, otherwise Name; provide a fallback.
        device_name_for_comment = device.get('ProductName') if device.get('ProductName') else device.get('Name', 'Unknown Ethernet')


        if vendor_id == "10EC": # Realtek
            if device_id == "8168" or device_id == "8111": # Common Gigabit Ethernet
                kext_name_to_use = "RealtekRTL8111"
            elif device_id == "8125": # Common 2.5 Gigabit Ethernet
                kext_name_to_use = "LucyRTL8125Ethernet"
            # Add more Realtek device IDs and their kexts if needed
        elif vendor_id == "8086": # Intel
            # Most Intel NICs are covered by IntelMausi, but some newer/older ones might need IntelSnowMausi or AppleIntelE1000e.
            # This is a simplification; a more robust check would involve specific Device IDs.
            kext_name_to_use = "IntelMausi" 
        # Add other vendors like Broadcom, Aquantia, etc.
        # elif vendor_id == "14E4": # Broadcom
            # if device_id == "xxxx": kext_name_to_use = "BCM5722D.kext" or similar
        
        if kext_name_to_use and kext_name_to_use not in added_kexts_set:
            if kext_name_to_use in KEXT_INFO_DB:
                kext_entry = KEXT_INFO_DB[kext_name_to_use].copy()
                kext_entry.update(COMMON_KEXT_PROPERTIES) # Apply common properties
                # Update comment to include actual device name and IDs
                kext_entry["Comment"] = f"{kext_entry.get('Comment', kext_name_to_use)} for {device_name_for_comment} (VID:{vendor_id} DID:{device_id})"
                
                kernel_add_entries.append(kext_entry)
                added_kexts_set.add(kext_name_to_use) # Ensure we only add one kext per type even if multiple similar NICs
                print(f"    Ethernet config: Planned to add {kext_name_to_use} for {device_name_for_comment}")
            else:
                print(f"    Warning: Kext info for '{kext_name_to_use}' not found in KEXT_INFO_DB.")

    ethernet_config_parts = {}
    if kernel_add_entries:
        ethernet_config_parts["Kernel"] = {"Add": kernel_add_entries}
    else:
        print("    No specific Ethernet kext identified for config.plist based on detected devices.")
        
    return ethernet_config_parts


if __name__ == "__main__":
    sample_cpu_info_alder_lake = {
        "python_version": "3.9.12.final.0 (64 bit)", "cpuinfo_version_string": "9.0.0",
        "brand_raw": "12th Gen Intel(R) Core(TM) i7-12700K",
        "hz_advertised_friendly": "3.6000 GHz", "hz_actual_friendly": "3.6084 GHz",
        "arch_string_raw": "X86_64", "vendor_id_raw": "GenuineIntel",
        "count": 20, "cores": 12, "flags": ["avx", "avx2"] 
    }
    sample_gpu_info_list_igpu_only = [{"Name": "Intel(R) UHD Graphics 770", "VendorID": "8086", "DeviceID": "4680"}]
    sample_gpu_info_list_igpu_and_nvidia = [
        {"Name": "Intel(R) UHD Graphics 770", "VendorID": "8086", "DeviceID": "4680"},
        {"Name": "NVIDIA GeForce GTX 970", "VendorID": "10DE", "DeviceID": "13C2"}
    ]
    sample_audio_device_list_realtek = [{"Name": "Realtek High Definition Audio", "PNPDeviceID": "HDAUDIO\\FUNC_01&VEN_10EC&DEV_0897", "VendorID": "10EC", "DeviceID": "0897"}]
    sample_ethernet_list_realtek_8111 = [{"ProductName": "Realtek PCIe GbE Family Controller", "VendorID": "10EC", "DeviceID": "8168"}]
    sample_ethernet_list_intel = [{"ProductName": "Intel(R) Ethernet Connection I219-V", "VendorID": "8086", "DeviceID": "15B8"}]


    def custom_json_serializer(obj):
        if isinstance(obj, bytes): return f"<bytes: {obj.hex() if obj else '(empty)'}>"
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

    print("--- Testing CPU Config Parts ---")
    cpu_parts = generate_cpu_config_parts(sample_cpu_info_alder_lake, target_smbios="iMacPro1,1")
    print(json.dumps(cpu_parts, indent=4, default=custom_json_serializer, sort_keys=True))

    print("\n--- Testing GPU Config Parts (iGPU only) ---")
    gpu_parts_igpu = generate_gpu_config_parts(sample_gpu_info_list_igpu_only, sample_cpu_info_alder_lake)
    print(json.dumps(gpu_parts_igpu, indent=4, default=custom_json_serializer, sort_keys=True))

    print("\n--- Testing GPU Config Parts (iGPU + NVIDIA GTX 970) ---")
    gpu_parts_dpgu = generate_gpu_config_parts(sample_gpu_info_list_igpu_and_nvidia, sample_cpu_info_alder_lake)
    print(json.dumps(gpu_parts_dpgu, indent=4, default=custom_json_serializer, sort_keys=True))

    print("\n--- Testing Audio Config Parts (Realtek ALC897) ---")
    audio_parts_realtek = generate_audio_config_parts(sample_audio_device_list_realtek)
    print(json.dumps(audio_parts_realtek, indent=4, default=custom_json_serializer, sort_keys=True))
    
    print("\n--- Testing Ethernet Config Parts (Realtek RTL8111/8168) ---")
    eth_parts_rtl = generate_ethernet_config_parts(sample_ethernet_list_realtek_8111)
    print(json.dumps(eth_parts_rtl, indent=4, default=custom_json_serializer, sort_keys=True))

    print("\n--- Testing Ethernet Config Parts (Intel Mausi) ---")
    eth_parts_intel = generate_ethernet_config_parts(sample_ethernet_list_intel)
    print(json.dumps(eth_parts_intel, indent=4, default=custom_json_serializer, sort_keys=True))

    print("\n--- Testing Empty Device Lists ---")
    gpu_empty = generate_gpu_config_parts([], sample_cpu_info_alder_lake)
    audio_empty = generate_audio_config_parts([])
    eth_empty = generate_ethernet_config_parts([])
    print("GPU Empty:", json.dumps(gpu_empty, indent=4, default=custom_json_serializer, sort_keys=True))
    print("Audio Empty:", json.dumps(audio_empty, indent=4, default=custom_json_serializer, sort_keys=True))
    print("Ethernet Empty:", json.dumps(eth_empty, indent=4, default=custom_json_serializer, sort_keys=True))
