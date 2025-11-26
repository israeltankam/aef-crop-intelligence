🛰️ AEF Crop Intelligence

AEF Crop Intelligence is a comprehensive Agricultural Digital Twin & Intelligence Platform designed to empower farmers and agronomists with data-driven insights. By combining mechanistic crop simulation models with real-time satellite observations, the platform provides actionable intelligence on crop health, stress factors, and yield potential.

🌟 Key Features

Digital Twin Simulation: Creates a virtual replica of your field to model crop growth, water balance, and nutrient dynamics.

Satellite Integration (AlphaEarth): Leverages Earth Engine (Sentinel-2, CHIRPS, ERA5-Land) for:

Automated Soil Retrieval: Fetches soil texture and organic carbon data based on location.

Local Climatology: Generates site-specific historical weather data for accurate simulations.

Reality Check: Validates model predictions against observed satellite NDVI vegetation indices.

Spatial Epidemiology: Models disease spread based on "Patient Zero" observations and environmental risk factors.

Smart Validation: Prevents configuration errors by validating field boundaries against land cover maps (ensuring fields aren't drawn on water or cities).

Actionable Reporting: Generates detailed PDF dossiers with yield forecasts, stress diagnostics, and management recommendations.

🛠️ Tech Stack

Frontend: Streamlit, Hydralit Components

Geospatial: Folium, Earth Engine API (Google), Geopy

Simulation Engine: Python (NumPy, Pandas, SciPy) - Custom STICS-lite implementation

Visualization: Altair, Matplotlib

Reporting: FPDF

🚀 Quick Start

Prerequisites

Python 3.10+

Google Earth Engine Account & Service Account Key

Installation

Clone the repository:


Install dependencies:

pip install -r requirements.txt


Configure Secrets:
Create a .streamlit/secrets.toml file in the root directory and add your Google Cloud Service Account credentials:

[gcp_service_account]
type = "service_account"
project_id = "your-project-id"
private_key_id = "your-key-id"
private_key = "-----BEGIN PRIVATE KEY-----\n..."
client_email = "your-service-account-email"
client_id = "your-client-id"
auth_uri = "[https://accounts.google.com/o/oauth2/auth](https://accounts.google.com/o/oauth2/auth)"
token_uri = "[https://oauth2.googleapis.com/token](https://oauth2.googleapis.com/token)"
auth_provider_x509_cert_url = "[https://www.googleapis.com/oauth2/v1/certs](https://www.googleapis.com/oauth2/v1/certs)"
client_x509_cert_url = "your-cert-url"


Run the App:

streamlit run app.py


📖 Usage

Site Setup: Use the wizard to define your field geometry, crop type, planting dates, and disease observations.

Intelligence Dashboard: Analyze the simulation results. Use the slider to view historical or future states. Check the "Reality Check" tab to compare the model against satellite data.

Report: Generate and download a comprehensive PDF report for offline use and decision-making.

🛡️ License & Rights

© 2025 Israël Tankam. All Rights Reserved.

This software and its associated documentation are the proprietary property of Israël Tankam. Unauthorized copying, distribution, modification, or use of this source code, via any medium, is strictly prohibited without express written permission from the copyright holder.

Powered by AlphaEarth Foundations