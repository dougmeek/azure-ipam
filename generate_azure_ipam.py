
# azure-ipam: Azure IP Address Management Extraction Tool
#
# Copyright (C) 2025  Doug Meek
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# ----------------------------------------------------------------------
# azure-ipam: Generate an Excel export of Azure VNet/subnet usage for
#             user-supplied CIDR ranges, including pie charts and
#             conditional formatting for easy visualization.
#
# Usage:
#   python generate_azure_ipam.py
#
# Requirements:
#   - azure-identity
#   - azure-mgmt-network
#   - azure-mgmt-resource
#   - ipaddress (standard library)
#   - pandas
#   - xlsxwriter
#   - tqdm (optional, for progress bars)
#
# Features:
#   - Prompts for one or more CIDR ranges to track.
#   - Scans all subscriptions, resource groups, VNets, and subnets.
#   - Reports all used and unused subnets within the provided ranges.
#   - Excel output includes:
#       * "Subnet Usage" sheet with pie charts for each range.
#       * "All_VNets" summary sheet.
#       * One sheet per CIDR range.
#       * Conditional formatting for Used, Unused, and No address space.
#       * Borders and freeze panes for readability.
#
# Author: Doug Meek
# License: GNU GPLv3
# ----------------------------------------------------------------------

import ipaddress
from datetime import datetime
from azure.identity import AzureCliCredential
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.resource import SubscriptionClient, ResourceManagementClient
import pandas as pd
import re

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

def get_user_cidrs():
    while True:
        cidrs = []
        print("\n----------------------------------------------------------------------------------------")
        print("\nEnter dedicated CIDRs for the Azure tenant (comma separated, e.g. 10.0.0.0/8, 192.168.0.0/16):")
        cidr_input = input("\n> ").strip()
        all_valid = True
        for cidr in map(str.strip, cidr_input.split(',')):
            if not cidr:
                continue
            if '/' not in cidr:
                print(f"\nInvalid CIDR: '{cidr}'. CIDR must include a prefix (e.g. 10.0.0.0/8).")
                all_valid = False
                break
            try:
                cidrs.append(ipaddress.ip_network(cidr))
            except ValueError:
                print(f"\nInvalid CIDR: '{cidr}'. Please enter valid CIDR ranges (e.g. 10.0.0.0/8, 192.168.0.0/16).")
                all_valid = False
                break
        if cidrs and all_valid:
            return cidrs
        print("\nPlease try again.")

def find_unused_subnets(parent_cidr, used_networks):
    used = sorted([ipaddress.ip_network(n) for n in used_networks], key=lambda n: (n.network_address, n.prefixlen))
    available = [parent_cidr]
    for u in used:
        new_available = []
        for a in available:
            if u.subnet_of(a):
                new_available.extend(a.address_exclude(u))
            else:
                new_available.append(a)
        available = new_available
    return available

def sort_ipam_dataframe(df):
    def ip_key(addr):
        try:
            return int(ipaddress.ip_network(addr).network_address)
        except Exception:
            return float('inf')
    if "Address" in df.columns:
        df = df.assign(_ip_sort=df["Address"].map(ip_key))
        df = df.sort_values(by=["_ip_sort", "CIDR Prefix", "Status"])
        df = df.drop(columns=["_ip_sort"])
    return df

def sanitize_sheet_name(name):
    name = re.sub(r'[\\/*?:\[\]]', '_', name)
    name = name.replace("'", "")
    return name[:31]

def autofit_columns(worksheet, dataframe):
    for idx, col in enumerate(dataframe.columns):
        max_len = max([len(str(s)) for s in dataframe[col].values] + [len(str(col))])
        worksheet.set_column(idx, idx, max_len + 2)

def excel_col_letter(idx):
    letters = ''
    while idx >= 0:
        letters = chr(idx % 26 + 65) + letters
        idx = idx // 26 - 1
    return letters

def apply_row_conditional_formatting(worksheet, df, used_format, unused_format, noaddr_format):
    if not df.empty and "Status" in df.columns:
        status_col_idx = df.columns.get_loc("Status")
        row_count = len(df)
        col_count = len(df.columns)
        status_col_letter = excel_col_letter(status_col_idx)
        for status, fmt in [
            ("Used", used_format),
            ("Unused", unused_format),
            ("No address space assigned", noaddr_format)
        ]:
            worksheet.conditional_format(
                1, 0, row_count, col_count - 1,
                {
                    'type': 'formula',
                    'criteria': f'=${status_col_letter}2="{status}"',
                    'format': fmt
                }
            )

def get_pie_data(user_cidrs, cidr_data):
    pie_data = []
    for cidr in user_cidrs:
        total_ips = ipaddress.ip_network(cidr).num_addresses
        used_ips = sum(
            ipaddress.ip_network(f"{row['Address']}/{row['CIDR Prefix']}").num_addresses
            for row in cidr_data[str(cidr)] if row["Status"] == "Used"
        )
        pie_data.append({
            "CIDR Range": str(cidr),
            "Allocated": used_ips,
            "Unallocated": max(total_ips - used_ips, 0)
        })
    return pie_data

def reorder_columns(df):
    cols = list(df.columns)
    if "IP Range" in cols:
        cols.remove("IP Range")
        idx = cols.index("CIDR Prefix") + 1
        cols = cols[:idx] + ["IP Range"] + cols[idx:]
        df = df[cols]
    return df

def add_borders(worksheet, df, workbook):
    border_format = workbook.add_format({'border': 1})
    header_border_format = workbook.add_format({'border': 2, 'bold': True, 'bg_color': '#F2F2F2'})
    row_count = len(df)
    col_count = len(df.columns)
    # Regular cell borders
    worksheet.conditional_format(
        1, 0, row_count, col_count - 1,
        {'type': 'no_blanks', 'format': border_format}
    )
    worksheet.conditional_format(
        1, 0, row_count, col_count - 1,
        {'type': 'blanks', 'format': border_format}
    )
    # Header thick border
    worksheet.conditional_format(
        0, 0, 0, col_count - 1,
        {'type': 'no_blanks', 'format': header_border_format}
    )
    worksheet.conditional_format(
        0, 0, 0, col_count - 1,
        {'type': 'blanks', 'format': header_border_format}
    )
    # Freeze header row
    worksheet.freeze_panes(1, 0)

def collect_azure_ipam_data(user_cidrs, credential):
    cidr_data = {str(cidr): [] for cidr in user_cidrs}
    used_subnets_map = {str(cidr): set() for cidr in user_cidrs}
    subscription_client = SubscriptionClient(credential)
    print("\n----------------------------------------------------------------------------------------")
    print("\nFetching Azure subscriptions...")
    subscriptions = list(subscription_client.subscriptions.list())
    subscriptions_iter = tqdm(subscriptions, desc="Subscriptions") if tqdm else subscriptions

    for sub in subscriptions_iter:
        sub_id = sub.subscription_id
        sub_name = sub.display_name
        print(f"\nProcessing subscription: {sub_name} ({sub_id})")
        network_client = NetworkManagementClient(credential, sub_id)
        resource_client = ResourceManagementClient(credential, sub_id)
        print("  Fetching resource groups...")
        resource_groups = list(resource_client.resource_groups.list())
        for rg in resource_groups:
            rg_name = rg.name
            print(f"    Processing resource group: {rg_name}")
            vnets = list(network_client.virtual_networks.list(rg_name))
            for vnet in vnets:
                vnet_name = vnet.name
                region = vnet.location
                print(f"      Processing VNet: {vnet_name} (region: {region})")
                for vnet_cidr in vnet.address_space.address_prefixes:
                    vnet_net = ipaddress.ip_network(vnet_cidr)
                    for user_cidr in user_cidrs:
                        if vnet_net.subnet_of(user_cidr):
                            cidr_data[str(user_cidr)].append({
                                "Address": str(vnet_net.network_address),
                                "CIDR Prefix": vnet_net.prefixlen,
                                "IP Range": f"{vnet_net.network_address} - {vnet_net.broadcast_address}",
                                "Subnet Name": "vnet-scope",
                                "VNet Name": vnet_name,
                                "Resource Group Name": rg_name,
                                "Subscription Name": sub_name,
                                "Region": region,
                                "Status": "Used"
                            })
                            used_subnets_map[str(user_cidr)].add(str(vnet_net))
                subnets = list(network_client.subnets.list(rg_name, vnet_name))
                for subnet in subnets:
                    if not subnet.address_prefix:
                        for user_cidr in user_cidrs:
                            cidr_data[str(user_cidr)].append({
                                "Address": "N/A",
                                "CIDR Prefix": "N/A",
                                "IP Range": "N/A",
                                "Subnet Name": subnet.name,
                                "VNet Name": vnet_name,
                                "Resource Group Name": rg_name,
                                "Subscription Name": sub_name,
                                "Region": region,
                                "Status": "No address space assigned"
                            })
                        continue
                    subnet_net = ipaddress.ip_network(subnet.address_prefix)
                    for user_cidr in user_cidrs:
                        if subnet_net.subnet_of(user_cidr):
                            cidr_data[str(user_cidr)].append({
                                "Address": str(subnet_net.network_address),
                                "CIDR Prefix": subnet_net.prefixlen,
                                "IP Range": f"{subnet_net.network_address} - {subnet_net.broadcast_address}",
                                "Subnet Name": subnet.name,
                                "VNet Name": vnet_name,
                                "Resource Group Name": rg_name,
                                "Subscription Name": sub_name,
                                "Region": region,
                                "Status": "Used"
                            })
                            used_subnets_map[str(user_cidr)].add(str(subnet_net))
    return cidr_data, used_subnets_map

def main():
    credential = AzureCliCredential()
    user_cidrs = get_user_cidrs()
    cidr_data, used_subnets_map = collect_azure_ipam_data(user_cidrs, credential)

    print("\nCalculating unused subnets for each CIDR...")
    for user_cidr in user_cidrs:
        print(f"  Calculating unused subnets for {user_cidr} ...")
        used_networks = used_subnets_map[str(user_cidr)]
        unused_subnets = find_unused_subnets(user_cidr, used_networks)
        for unused in unused_subnets:
            cidr_data[str(user_cidr)].append({
                "Address": str(unused.network_address),
                "CIDR Prefix": unused.prefixlen,
                "IP Range": f"{unused.network_address} - {unused.broadcast_address}",
                "Subnet Name": "",
                "VNet Name": "",
                "Resource Group Name": "",
                "Subscription Name": "",
                "Region": "",
                "Status": "Unused"
            })

    all_vnets_rows = []
    for cidr, data in cidr_data.items():
        for row in data:
            if row.get("Subnet Name") == "vnet-scope" or row.get("Status") == "Unused":
                vnet_row = row.copy()
                vnet_row["CIDR Range"] = cidr
                all_vnets_rows.append(vnet_row)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"ipam_tracking_{timestamp}.xlsx"
    print(f"\nWriting results to {filename} ...")
    with pd.ExcelWriter(filename, engine='xlsxwriter') as writer:
        workbook = writer.book
        used_format = workbook.add_format({'bg_color': "#FFBD80"})  # Light orange
        unused_format = workbook.add_format({'bg_color': '#C6EFCE'})  # Light green
        noaddr_format = workbook.add_format({'bg_color': '#FFCCCC'})  # Light red

        # Pie chart data and sheet
        pie_data = get_pie_data(user_cidrs, cidr_data)
        df_pie = pd.DataFrame(pie_data)
        df_pie.to_excel(writer, sheet_name="Subnet Usage", index=False)
        worksheet_pie = writer.sheets["Subnet Usage"]
        autofit_columns(worksheet_pie, df_pie)
        add_borders(worksheet_pie, df_pie, workbook)
        chart_row = 1
        for idx, pie_row in df_pie.iterrows():
            chart = workbook.add_chart({'type': 'pie'})
            chart.add_series({
                'name':       f"Subnet Usage for {pie_row['CIDR Range']}",
                'categories': ['Subnet Usage', 0, 1, 0, 2],
                'values':     ['Subnet Usage', idx + 1, 1, idx + 1, 2],
                'points': [
                    {'fill': {'color': '#FFD580'}},
                    {'fill': {'color': '#C6EFCE'}},
                ],
                'data_labels': {'percentage': True, 'category': True}
            })
            chart.set_title({'name': f"Subnet Usage: {pie_row['CIDR Range']}"})
            worksheet_pie.insert_chart(chart_row, 4, chart, {'x_scale': 1.2, 'y_scale': 1.2})
            chart_row += 18

        # All_VNets summary sheet
        if all_vnets_rows:
            df_vnets = pd.DataFrame(all_vnets_rows)
            if "CIDR Range" in df_vnets.columns:
                cols = list(df_vnets.columns)
                cols.insert(0, cols.pop(cols.index("CIDR Range")))
                df_vnets = df_vnets[cols]
            df_vnets = sort_ipam_dataframe(df_vnets)
            df_vnets = reorder_columns(df_vnets)
            df_vnets.to_excel(writer, sheet_name="All_VNets", index=False)
            worksheet = writer.sheets["All_VNets"]
            autofit_columns(worksheet, df_vnets)
            add_borders(worksheet, df_vnets, workbook)
            apply_row_conditional_formatting(worksheet, df_vnets, used_format, unused_format, noaddr_format)

        # Per-CIDR sheets
        for cidr, data in cidr_data.items():
            print(f"  Writing worksheet for {cidr} ...")
            df = pd.DataFrame(data)
            if not df.empty:
                df = sort_ipam_dataframe(df)
                df = reorder_columns(df)
            sheet_name = sanitize_sheet_name(cidr.replace('/', '_'))
            df.to_excel(writer, sheet_name=sheet_name, index=False)
            worksheet = writer.sheets[sheet_name]
            autofit_columns(worksheet, df)
            add_borders(worksheet, df, workbook)
            apply_row_conditional_formatting(worksheet, df, used_format, unused_format, noaddr_format)

    print(f"\nIPAM tracking spreadsheet saved as {filename}\n")

if __name__ == "__main__":
    main()
