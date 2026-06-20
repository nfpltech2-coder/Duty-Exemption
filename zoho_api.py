import os
import sys
import requests
from pathlib import Path
from dotenv import load_dotenv
from typing import Optional, Tuple

class ShaktiCreatorAPI:
    def __init__(self):
        if getattr(sys, 'frozen', False):
            _env_dir = Path(sys.executable).parent
        else:
            _env_dir = Path(__file__).resolve().parent
            
        load_dotenv(_env_dir / ".env")
        
        self.client_id = os.getenv("ZOHO_CLIENT_ID")
        self.client_secret = os.getenv("ZOHO_CLIENT_SECRET")
        self.refresh_token = os.getenv("ZOHO_REFRESH_TOKEN")
        self.account_owner = os.getenv("ZOHO_ACCOUNT_OWNER")
        self.app_link_name = os.getenv("ZOHO_APP_LINK_NAME")
        self.form_link_name = os.getenv("ZOHO_FORM_LINK_NAME")
        self.report_link_name = os.getenv("ZOHO_REPORT_LINK_NAME")
        self.auth_domain = os.getenv("ZOHO_AUTH_DOMAIN", "accounts.zoho.in")
        self.api_domain = os.getenv("ZOHO_API_DOMAIN", "creator.zoho.in")
        self.attachment_field_name = os.getenv("ZOHO_ATTACHMENT_FIELD_NAME", "Attachment")
        
        if not self.refresh_token:
            raise ValueError("ZOHO_REFRESH_TOKEN is missing from .env")
            
        self.access_token = None
        self.base_url = f"https://{self.api_domain}/api/v2/{self.account_owner}/{self.app_link_name}"
        
        self._refresh_access_token()
        
    def _refresh_access_token(self):
        url = f"https://{self.auth_domain}/oauth/v2/token"
        payload = {
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "refresh_token"
        }
        
        response = requests.post(url, data=payload)
        response.raise_for_status()
        data = response.json()
        
        if "access_token" in data:
            self.access_token = data["access_token"]
        else:
            raise ValueError(f"Failed to refresh token: {data}")
            
    def get_headers(self):
        return {
            "Authorization": f"Zoho-oauthtoken {self.access_token}",
            "Content-Type": "application/json"
        }
        
    def get_record_by_be(self, be_no: str) -> Tuple[Optional[str], str, Optional[float]]:
        """Find the record ID for a given BE No in Shakti.
        Returns: (record_id, status_code, existing_duty_exempted_value)
        existing_duty_exempted_value is None when record not found or field is empty.
        """
        url = f"{self.base_url}/report/{self.report_link_name}"
        params = {
            "criteria": f'(BE_No.BE_No == {be_no})'
        }
        
        try:
            response = requests.get(url, headers=self.get_headers(), params=params)
            
            if response.status_code == 404:
                return None, "NO_RECORD", None
                
            response.raise_for_status()
            data = response.json()
            
            records = data.get("data", [])
            if not records:
                return None, "NO_RECORD", None
                
            if len(records) > 1:
                return None, "DUPLICATE_RECORD", None
            
            record = records[0]
            record_id = record.get("ID")
            
            # Read existing Duty_exempted value (may be 0, empty string, or a number)
            raw_duty = record.get("Duty_exempted", None)
            existing_duty: Optional[float] = None
            if raw_duty not in (None, "", 0, "0", "0.0", "0.00"):
                try:
                    existing_duty = float(raw_duty)
                except (ValueError, TypeError):
                    existing_duty = None
            
            return record_id, "OK", existing_duty
            
        except requests.exceptions.RequestException as e:
            return None, f"NETWORK_ERROR: {str(e)}", None

            
    def update_duty_exempted(self, record_id: str, exempted_duty: float) -> Tuple[bool, str]:
        """Update the Duty_exempted field for a specific record."""
        url = f"{self.base_url}/report/{self.report_link_name}/{record_id}"
        
        # Duty_exempted is an Amount field. Formatting to 2 decimal places.
        formatted_duty = f"{exempted_duty:.2f}"
        
        payload = {
            "data": {
                "Duty_exempted": formatted_duty
            }
        }
        
        try:
            # Zoho Creator update uses PATCH
            response = requests.patch(url, headers=self.get_headers(), json=payload)
            
            if response.status_code in [200, 202, 204]:
                try:
                    res_data = response.json()
                    top_code = res_data.get("code")
                    if top_code is not None and top_code != 3000:
                        return False, f"ZOHO_ERR_{top_code}: {res_data.get('message', 'API Error')}"
                    
                    if "data" in res_data and isinstance(res_data["data"], dict):
                        field_res = res_data["data"].get("Duty_exempted")
                        if isinstance(field_res, dict):
                            code = field_res.get("code")
                            if code is not None and code != 3000:
                                msg = field_res.get("message", "Field update error")
                                return False, f"ZOHO_ERR_{code}: {msg}"
                except Exception:
                    pass
                return True, "OK"
            
            try:
                error_msg = response.json()
            except Exception:
                error_msg = response.text
                
            return False, f"API_ERROR: {error_msg}"
            
        except requests.exceptions.RequestException as e:
            return False, f"NETWORK_ERROR: {str(e)}"

    def upload_attachment(self, record_id: str, file_path: str) -> Tuple[bool, str]:
        """
        Uploads a file to the Attachment field of a specific record via multipart POST.
        Does NOT include Content-Type header so requests sets the correct boundary automatically.
        """
        url = (
            f"{self.base_url}/report/{self.report_link_name}"
            f"/{record_id}/{self.attachment_field_name}/upload"
        )

        try:
            with open(file_path, "rb") as f:
                file_name = Path(file_path).name
                files = {
                    "file": (
                        file_name,
                        f,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                }
                # Authorization only – requests sets multipart Content-Type + boundary
                headers = {"Authorization": f"Zoho-oauthtoken {self.access_token}"}
                response = requests.post(url, headers=headers, files=files)

            if response.status_code in [200, 201, 202]:
                try:
                    res_data = response.json()
                    top_code = res_data.get("code")
                    if top_code is not None and top_code != 3000:
                        return False, f"ATTACH_ERR_{top_code}: {res_data.get('message', 'Upload Error')}"
                except Exception:
                    pass
                return True, "OK"

            try:
                error_msg = response.json()
            except Exception:
                error_msg = response.text
            return False, f"ATTACH_API_ERROR: {error_msg}"

        except Exception as e:
            return False, f"ATTACH_ERROR: {str(e)}"
