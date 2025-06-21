# Azure IP Address Management Extraction Tool

This script scans your Azure tenant for used subnets and VNet address allocations, then generates a spreadsheet for IP address management (IPAM) tracking.

This tool was written to give me visibility and help me better understand and manage my own environment. Hopefully it helps you as well.

## Features

- Prompts for a list of dedicated CIDRs to track.
- Scans all subscriptions, VNets, and subnets in your Azure tenant.
- Outputs an Excel file with:
  - A **"Subnet Usage"** sheet with pie charts visualizing allocated and unallocated IPs for each CIDR range.
  - An **"All_VNets"** summary sheet showing all VNet and unused allocations.
  - One worksheet per input CIDR range, listing all used, unused, and unassigned subnets.
- Each worksheet contains the following columns:
  - Address
  - CIDR Prefix
  - IP Range (Start IP - End IP)
  - Subnet Name (`vnet-scope` for VNet allocations)
  - VNet Name
  - Resource Group Name
  - Subscription Name
  - Region
  - Status (`Used`, `Unused`, or `No address space assigned`)
- Conditional formatting:
  - Used rows: light orange
  - Unused rows: light green
  - No address space assigned: light red
- Borders around all cells, with thick borders and freeze panes for headers.
- The export file is named with the current date and time, e.g. `ipam_tracking_20250621_153045.xlsx`.

## Prerequisites

- Python 3.7+
- Azure CLI (`az login` must be completed)
- Required Python packages (see below)

## Installation

1. Clone or download this repository.

2. **(Recommended)** Create and activate a Python virtual environment:
   ```sh
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install dependencies:
   ```sh
   pip install -r requirements.txt
   ```

## Usage

1. Authenticate with Azure CLI:
   ```sh
   az login
   ```
2. Run the script:
   ```sh
   python generate_azure_ipam.py
   ```
3. Enter your dedicated CIDRs when prompted (comma separated, e.g. `10.0.0.0/8, 192.168.0.0/16`).

4. The output file (e.g. `ipam_tracking_YYYYMMDD_HHMMSS.xlsx`) will be created in the current directory.  
   - The **"Subnet Usage"** sheet provides a pie chart for each CIDR range.
   - The **"All_VNets"** sheet summarizes all VNet and unused allocations.
   - Each CIDR worksheet details all used, unused, and unassigned subnets.

## Notes

- The script lists all used subnets and VNet allocations within the provided CIDRs.
- Unused subnets are calculated and visualized for each CIDR.
- Subnets with no address space assigned are included with placeholder text and highlighted.
- All columns auto-fit to their content.
- To deactivate the virtual environment when finished:
  ```sh
  deactivate
  ```

## License

This project is licensed under the GNU General Public License v3.0.
