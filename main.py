from flask import Flask, render_template, request, redirect, url_for, session, flash
import os
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
import yaml
from datetime import datetime, timedelta
import os

from dotenv import load_dotenv

load_dotenv() 

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY')

# Configuration
GOOGLE_ADS_CONFIG = {
    'developer_token': os.getenv('GOOGLE_ADS_DEVELOPER_TOKEN'),
    'client_id': os.getenv('GOOGLE_ADS_CLIENT_ID'),
    'client_secret': os.getenv('GOOGLE_ADS_CLIENT_SECRET'),
    'refresh_token': os.getenv('GOOGLE_ADS_REFRESH_TOKEN'),
    'login_customer_id': os.getenv('GOOGLE_ADS_LOGIN_CUSTOMER_ID')
}

class GoogleAdsManager:
    def __init__(self):
        self.client = None
    
    def initialize_client(self, config):
        """Initialize Google Ads client with proper credentials"""
        try:
            # Create yaml config for Google Ads client
            yaml_config = {
                'developer_token': config['developer_token'],
                'client_id': config['client_id'],
                'client_secret': config['client_secret'],
                'refresh_token': config['refresh_token'],
                'login_customer_id': config['login_customer_id'],
                'use_proto_plus': True
            }
            
            # Save to temporary file
            with open('google-ads.yaml', 'w') as f:
                yaml.dump(yaml_config, f)
            
            self.client = GoogleAdsClient.load_from_storage('google-ads.yaml')
            return True
        except Exception as e:
            print(f"Error initializing client: {e}")
            return False
    
    def get_campaign_spend_data(self, customer_id, date_range_days=30):
        """Fetch campaign spend data for the specified date range"""
        if not self.client:
            return None
        
        try:
            ga_service = self.client.get_service("GoogleAdsService")
            
            # Calculate date range
            end_date = datetime.now()
            start_date = end_date - timedelta(days=date_range_days)
            
            query = f"""
                SELECT 
                    campaign.id,
                    campaign.name,
                    metrics.cost_micros,
                    metrics.impressions,
                    metrics.clicks,
                    segments.date
                FROM campaign 
                WHERE segments.date BETWEEN '{start_date.strftime('%Y-%m-%d')}' 
                AND '{end_date.strftime('%Y-%m-%d')}'
                ORDER BY segments.date DESC
            """
            
            response = ga_service.search(customer_id=customer_id, query=query)
            
            campaigns_data = []
            for row in response:
                campaigns_data.append({
                    'campaign_id': row.campaign.id,
                    'campaign_name': row.campaign.name,
                    'date': row.segments.date,
                    'cost': row.metrics.cost_micros / 1_000_000,  # Convert micros to currency
                    'impressions': row.metrics.impressions,
                    'clicks': row.metrics.clicks
                })
            
            return campaigns_data
        
        except GoogleAdsException as ex:
            print(f"Request failed with status {ex.error.code().name}")
            for error in ex.failure.errors:
                print(f"\tError with message: {error.message}")
            return None
        except Exception as e:
            print(f"An error occurred: {e}")
            return None

ads_manager = GoogleAdsManager()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/setup', methods=['GET', 'POST'])
def setup():
    if request.method == 'POST':
        config = {
            'developer_token': request.form.get('developer_token'),
            'client_id': request.form.get('client_id'),
            'client_secret': request.form.get('client_secret'),
            'refresh_token': request.form.get('refresh_token'),
            'login_customer_id': request.form.get('login_customer_id')
        }
        
        if ads_manager.initialize_client(config):
            session['ads_configured'] = True
            flash('Google Ads API configured successfully!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Failed to configure Google Ads API. Please check your credentials.', 'error')
    
    return render_template('setup.html')

@app.route('/dashboard')
def dashboard():
    if not session.get('ads_configured'):
        flash('Please configure your Google Ads API credentials first.', 'warning')
        return redirect(url_for('setup'))
    
    return render_template('dashboard.html')

@app.route('/fetch_data', methods=['POST'])
def fetch_data():
    if not session.get('ads_configured'):
        return redirect(url_for('setup'))
    
    customer_id = request.form.get('customer_id')
    date_range = int(request.form.get('date_range', 30))
    
    if not customer_id:
        flash('Please provide a customer ID.', 'error')
        return redirect(url_for('dashboard'))
    
    # Remove any formatting from customer ID
    customer_id = customer_id.replace('-', '').replace(' ', '')
    
    spend_data = ads_manager.get_campaign_spend_data(customer_id, date_range)
    
    if spend_data:
        # Calculate totals
        total_spend = sum(item['cost'] for item in spend_data)
        total_clicks = sum(item['clicks'] for item in spend_data)
        total_impressions = sum(item['impressions'] for item in spend_data)
        
        return render_template('results.html', 
                             spend_data=spend_data,
                             total_spend=total_spend,
                             total_clicks=total_clicks,
                             total_impressions=total_impressions,
                             customer_id=customer_id,
                             date_range=date_range)
    else:
        flash('Failed to fetch data. Please check your customer ID and try again.', 'error')
        return redirect(url_for('dashboard'))