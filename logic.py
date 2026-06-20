import pandas as pd
from typing import List, Dict, Any
import json
import os
import sys

class MissingCTHError(Exception):
    def __init__(self, missing_cths: list):
        self.missing_cths = missing_cths
        super().__init__(f"Missing duty rates for CTHs: {missing_cths}")

def get_duty_rates_file():
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, 'duty_rates.json')

def load_duty_rates() -> Dict[int, float]:
    file_path = get_duty_rates_file()
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            rates_str = json.load(f)
            rates = {}
            for k, v in rates_str.items():
                try:
                    rates[int(k)] = float(v)
                except ValueError:
                    pass
            return rates
    else:
        default_rates = {
            61161000: 0.20,
            40151900: 0.10,
            40151200: 0.10
        }
        save_duty_rates(default_rates)
        return default_rates

def save_duty_rates(rates: Dict[int, float]):
    file_path = get_duty_rates_file()
    with open(file_path, 'w') as f:
        json.dump(rates, f, indent=4)

def process_duty_exemption(file_path: str) -> tuple[List[Dict[str, Any]], str]:
    """
    Reads the 'Master Data' sheet, identifies records where 'Total Basic Duty (INR)' == 0,
    calculates the Exempted Duty based on CTH rate mapping, aggregates it by 'BE No',
    and returns a tuple of (aggregated_results, sheet_name_used).
    """
    try:
        xls = pd.ExcelFile(file_path)
        sheet_names = xls.sheet_names
        
        # Find sheet name case-insensitively
        cleaned_sheets = [s.strip().lower() for s in sheet_names]
        
        if "master data" in cleaned_sheets:
            target_sheet = sheet_names[cleaned_sheets.index("master data")]
        elif "sheet 1" in cleaned_sheets:
            target_sheet = sheet_names[cleaned_sheets.index("sheet 1")]
        elif "sheet1" in cleaned_sheets:
            target_sheet = sheet_names[cleaned_sheets.index("sheet1")]
        else:
            target_sheet = sheet_names[0]
            
        df = pd.read_excel(xls, sheet_name=target_sheet)
    except Exception as e:
        raise ValueError(f"Could not read excel file: {e}")


    # Required columns
    required_columns = ['BE No', 'BE Date', 'CTH', 'Assessable Value (INR)', 'Total Basic Duty (INR)', 'Job No']
    
    # Clean the column names
    df.columns = df.columns.str.strip()
    
    for col in required_columns:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")

    duty_rates = load_duty_rates()

    # Clean the column and filter
    df['Total Basic Duty (INR)'] = pd.to_numeric(df['Total Basic Duty (INR)'], errors='coerce')
    filtered_df = df[df['Total Basic Duty (INR)'] == 0].copy()

    if filtered_df.empty:
        return [], target_sheet

    # Check for missing CTHs first
    missing_cths = set()
    for _, row in filtered_df.iterrows():
        cth = row['CTH']
        try:
            cth_val = int(cth)
            if cth_val not in duty_rates:
                missing_cths.add(cth_val)
        except (ValueError, TypeError):
            continue

    if missing_cths:
        raise MissingCTHError(list(missing_cths))


    results_by_be = {}

    for _, row in filtered_df.iterrows():
        be_no = row['BE No']
        if pd.isna(be_no):
            continue
            
        # Ensure BE No is string and remove decimals if it was read as float
        be_str = str(be_no).strip()
        if be_str.endswith('.0'):
            be_str = be_str[:-2]

        job_no = row['Job No']
        job_str = "" if pd.isna(job_no) else str(job_no).strip()
        if job_str.endswith('.0'):
            job_str = job_str[:-2]

        be_date = row['BE Date']
        be_datetime = pd.to_datetime(be_date, errors='coerce')
        if pd.isna(be_datetime):
            be_date_str = ""
        else:
            be_date_str = be_datetime.strftime('%d-%m-%Y')

        cth = row['CTH']
        try:
            cth_val = int(cth)
        except (ValueError, TypeError):
            continue

        if cth_val not in duty_rates:
            continue

        assessable_value = pd.to_numeric(row['Assessable Value (INR)'], errors='coerce')
        if pd.isna(assessable_value):
            continue

        rate = duty_rates[cth_val]
        basic_duty = assessable_value * rate
        sws = basic_duty * 0.10
        exempted_duty = basic_duty + sws

        if be_str not in results_by_be:
            results_by_be[be_str] = {
                'BE No': be_str,
                'Job No': job_str,
                'BE Date Raw': be_datetime,  # Used for sorting
                'BE Date': be_date_str,
                'Row Count': 0,
                'Total Exempted Duty': 0.0
            }
        
        results_by_be[be_str]['Row Count'] += 1
        results_by_be[be_str]['Total Exempted Duty'] += exempted_duty

    # Sort results by BE Date (ascending)
    final_results = list(results_by_be.values())
    final_results.sort(key=lambda x: x['BE Date Raw'] if not pd.isna(x['BE Date Raw']) else pd.Timestamp.max)
    return final_results, target_sheet


def generate_filtered_excel(input_file_path: str, sheet_name: str, be_no: str, output_file_path: str):
    """
    Creates a new Excel file containing only the rows matching the specified BE No
    from the original file, maintaining columns and sheet structure.
    """
    # Read the excel file
    xls = pd.ExcelFile(input_file_path)
    df = pd.read_excel(xls, sheet_name=sheet_name)
    
    # Filter rows with matching BE No
    df.columns = df.columns.str.strip()
    
    # Create temp string column for comparison
    df['BE No Temp'] = df['BE No'].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    
    clean_be_no = str(be_no).strip().replace('.0', '')
    filtered_df = df[df['BE No Temp'] == clean_be_no].copy()
    
    # Drop temp comparison column
    filtered_df = filtered_df.drop(columns=['BE No Temp'])
    
    # Write to new Excel file
    with pd.ExcelWriter(output_file_path, engine='openpyxl') as writer:
        filtered_df.to_excel(writer, sheet_name=sheet_name, index=False)

