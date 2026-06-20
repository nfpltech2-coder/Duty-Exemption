# Ansell Duty Exemption Updater

A desktop application designed for Nagarkot Forwarders Pvt. Ltd. to automate the calculation of exempted duty amounts from customs reports and synchronize them with the Zoho "Shakti" Creator platform.

## Features
- **Excel Data Processing:** Ingests master data sheets, aggregates assessable values by `BE No` for rows where `Total Basic Duty (INR)` is exactly zero.
- **Dynamic Duty Rate Engine:** Custom `duty_rates.json` mapping system to calculate basic duty and Social Welfare Surcharge (SWS). Includes an intuitive GUI to add and edit CTH-based percentage mappings.
- **Zoho Creator API Integration:** Validates records by `BE No` to avoid duplicate updates, checks for existing data to prevent overwriting, and patches the `Duty_exempted` field.
- **Interactive UI:** Built with Tkinter, featuring sortable tables, dynamic status indicators, a month-picker for granular syncing, and robust visual error tracking.

## Technical Stack
- **Python 3.10+**
- **GUI:** `tkinter`
- **Data Manipulation:** `pandas`, `openpyxl`
- **API Communication:** `requests`
- **Environment Management:** `python-dotenv`

## Installation

### Development Setup
1. Clone the repository.
2. Ensure Python 3.10 is installed.
3. Activate a virtual environment:
   ```bash
   venv\Scripts\activate
   ```
4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
5. Configure Environment Variables:
   - Create a `.env` file based on `.env.example`.
   - Populate it with valid Zoho Creator API credentials (Client ID, Secret, Refresh Token, Form Link Names).

### Building the Executable
To package the app into a standalone Windows executable with bundled `.env` access:
```bash
pyinstaller --noconfirm --onefile --windowed --add-data ".env;." --name "Duty Exemption Updater" app.py
```
*Note: Make sure your `.env` is accurate before building, as it will be embedded into the executable.*

## Architecture
- **`app.py`:** Main GUI application. Handles file upload dialogues, treeview populations, threaded API sync calls, and the Duty Rates management interface.
- **`logic.py`:** Pure data-processing functions. Extracts and groups Pandas dataframes. Includes custom exception handling (`MissingCTHError`) to interrupt flow for unknown customs tariffs.
- **`zoho_api.py`:** Dedicated API wrapper for Shakti. Handles token generation, duplicate identification, and field-level updates.

## Deployment
Share the `.exe` along with `duty_rates.json`. If `duty_rates.json` does not exist, the app will generate a fresh config file upon first run.
