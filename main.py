import streamlit as st
import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, date, timedelta
import requests
import json
from io import BytesIO
import time
import firebase_admin
from firebase_admin import credentials, firestore
import hashlib
import secrets
import streamlit.components.v1 as components
import re  # For password strength validation

# Page configuration
st.set_page_config(
    page_title="FitVerse - Complete Fitness Tracker",
    page_icon="logoo.png",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ===================== PASSWORD SECURITY HELPER FUNCTIONS =====================
def is_strong_password(password):
    """Check if password meets strength requirements"""
    if len(password) < 12:
        return False, "Password must be at least 12 characters"
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain uppercase letters"
    if not re.search(r'[a-z]', password):
        return False, "Password must contain lowercase letters"
    if not re.search(r'[0-9]', password):
        return False, "Password must contain numbers"
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False, "Password must contain special characters"
    return True, ""

def is_password_breached(password, timeout=2.0):
    """Check password against breached databases using HIBP API"""
    try:
        # Hash password using SHA-1
        sha1hash = hashlib.sha1(password.encode()).hexdigest().upper()
        prefix, suffix = sha1hash[:5], sha1hash[5:]
        
        # Make API request with timeout
        response = requests.get(
            f"https://api.pwnedpasswords.com/range/{prefix}",
            timeout=timeout
        )
        
        # Check if suffix exists in response
        if response.status_code == 200:
            for line in response.text.splitlines():
                if line.split(':')[0] == suffix:
                    return True
    except (requests.exceptions.RequestException, ValueError):
        # Fail safely if API is unavailable
        return False
    return False

# Define collection/document structure for Firestore
USER_DATA_COLLECTION = "users"
FOOD_DIARY_SUBCOLLECTION = "food_diary"
EXERCISE_LOG_SUBCOLLECTION = "exercise_log"
WEIGHT_LOG_SUBCOLLECTION = "weight_log"
WATER_LOG_SUBCOLLECTION = "water_log"
PROFILE_DOCUMENT = "profile"
GOALS_DOCUMENT = "goals"

# Define the column names for each DataFrame
FOOD_DIARY_COLS = ['date', 'meal', 'food_name', 'brand', 'calories', 'protein', 
                  'carbs', 'fat', 'fiber', 'quantity', 'serving_size']
EXERCISE_LOG_COLS = ['date', 'activity', 'duration_min', 'calories_burned', 'intensity']
WEIGHT_LOG_COLS = ['date', 'weight_kg']
WATER_LOG_COLS = ['date', 'glasses']

# Custom CSS for better UI
st.markdown("""
<style>
    .stMetric {
        background-color: black;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }            
    .success-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        color: #155724;
    }
    .warning-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #fff3cd;
        border: 1px solid #ffeeba;
        color: #856404;
    }
    .auth-container {
        display: flex;
        justify-content: center;
        align-items: center;
        padding: 2rem;
        border-radius: 10px;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        margin: 2rem 0;
    }
    .auth-button {
        background: white;
        color: #333;
        padding: 0.75rem 2rem;
        border: none;
        border-radius: 50px;
        font-weight: bold;
        text-decoration: none;
        transition: all 0.3s ease;
        box-shadow: 0 4px 15px rgba(0,0,0,0.2);
    }
    .auth-button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(0,0,0,0.3);
    }
    .debug-info {
        padding: 15px;
        background-color: #f8f9fa;
        border-radius: 5px;
        border: 1px solid #dee2e6;
        margin-bottom: 15px;
    }
    .profile-section {
        background-color: #f0f2f6;
        border-radius: 10px;
        padding: 20px;
        margin-bottom: 20px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .security-warning {
        background-color: #fff3cd;
        border-left: 6px solid #ff9800;
        padding: 16px;
        border-radius: 4px;
        margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)

# Initialize Firebase
@st.cache_resource
def init_firebase():
    """Initialize Firebase Admin SDK"""
    if not firebase_admin._apps:
        try:
            # Try to get service account from secrets
            service_account_info = json.loads(st.secrets["firebase"]["service_account"])
            cred = credentials.Certificate(service_account_info)
            firebase_admin.initialize_app(cred)
            return firestore.client()
        except Exception as e:
            st.error(f"Failed to initialize Firebase: {e}")
            return None
    return firestore.client()

# Initialize Firestore
db = init_firebase()

# ========================= FIREBASE AUTHENTICATION FUNCTIONS =========================

def firebase_sign_in(email, password):
    """Sign in user with email/password using Firebase REST API"""
    api_key = st.secrets["firebase"]["api_key"]
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={api_key}"
    
    payload = {
        "email": email,
        "password": password,
        "returnSecureToken": True
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            data = response.json()
            
            # Store tokens in session state
            st.session_state.id_token = data["idToken"]
            st.session_state.refresh_token = data["refreshToken"]
            
            # Check if password is breached
            if is_password_breached(password):
                st.session_state.password_breach_warning = True
            
            return {
                "id": data["localId"],
                "email": data["email"],
                "id_token": data["idToken"],
                "refresh_token": data["refreshToken"]
            }
        else:
            error_msg = response.json().get("error", {}).get("message", "Unknown error")
            st.error(f"Sign in failed: {error_msg}")
    except Exception as e:
        st.error(f"Authentication error: {e}")
    return None

def firebase_sign_up(email, password):
    """Create new user with enhanced password security"""
    # Validate password strength
    is_strong, strength_msg = is_strong_password(password)
    if not is_strong:
        st.error(f"Password too weak: {strength_msg}")
        return None
        
    # Check if password is breached
    if is_password_breached(password):
        st.error("This password was found in data breaches. Please choose a different one.")
        return None
        
    # Proceed with Firebase registration
    api_key = st.secrets["firebase"]["api_key"]
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={api_key}"
    
    payload = {
        "email": email,
        "password": password,
        "returnSecureToken": True
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            data = response.json()
            
            # Store tokens in session state
            st.session_state.id_token = data["idToken"]
            st.session_state.refresh_token = data["refreshToken"]
            
            return {
                "id": data["localId"],
                "email": data["email"],
                "id_token": data["idToken"],
                "refresh_token": data["refreshToken"]
            }
        else:
            error_msg = response.json().get("error", {}).get("message", "Unknown error")
            st.error(f"Sign up failed: {error_msg}")
    except Exception as e:
        st.error(f"Registration error: {e}")
    return None

def firebase_reset_password(email):
    """Send password reset email using Firebase REST API"""
    api_key = st.secrets["firebase"]["api_key"]
    if not api_key:
        return False, "Configuration error. Please contact support."
        
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:sendOobCode?key={api_key}"
    
    payload = {
        "requestType": "PASSWORD_RESET",
        "email": email
    }
    
    # Custom error messages
    error_messages = {
        "EMAIL_NOT_FOUND": "This email is not registered. Please sign up first.",
        "MISSING_EMAIL": "Please enter your email address.",
        "INVALID_EMAIL": "The email address is invalid. Please check your input.",
        "TOO_MANY_ATTEMPTS_TRY_LATER": "Too many attempts. Please try again later.",
        "USER_DISABLED": "This account has been disabled. Contact support for help."
    }
    
    try:
        # Improved retry mechanism with exponential backoff
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.post(url, json=payload, timeout=10)
                if response.status_code == 200:
                    return True, "Password reset email sent! Please check your inbox and spam folder."
                
                # Handle specific Firebase errors
                error_data = response.json()
                error_code = error_data.get("error", {}).get("message", "")
                
                if error_code in error_messages:
                    return False, error_messages[error_code]
                
                return False, f"Error: {error_code} - Please try again later."
                
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    time.sleep(wait_time)
                    continue
                return False, "Network error: Failed to connect to authentication service."
                
    except Exception as e:
        return False, f"Unexpected error: {str(e)}"
    
    return False, "Unknown error occurred."

def firebase_change_password(new_password):
    """Change password with security checks"""
    # Validate password strength
    is_strong, strength_msg = is_strong_password(new_password)
    if not is_strong:
        return False, f"Password too weak: {strength_msg}"
        
    # Check if password is breached
    if is_password_breached(new_password):
        return False, "This password was found in data breaches. Please choose a different one."
    
    # Update password via Firebase API
    api_key = st.secrets["firebase"]["api_key"]
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:update?key={api_key}"
    
    payload = {
        "idToken": st.session_state.id_token,
        "password": new_password,
        "returnSecureToken": True
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            # Update session with new tokens
            data = response.json()
            st.session_state.id_token = data["idToken"]
            st.session_state.refresh_token = data["refreshToken"]
            return True, "Password changed successfully!"
        else:
            error_msg = response.json().get("error", {}).get("message", "Unknown error")
            return False, f"Password change failed: {error_msg}"
    except Exception as e:
        return False, f"Error: {str(e)}"

def show_password_security_warning():
    """Display security warning and password change form"""
    st.title("⚠️ Security Alert")
    
    st.markdown("""
    <div class="security-warning">
        <h3>Your password was found in a data breach</h3>
        <p>To protect your account, you must change your password immediately.</p>
        <p>This password has been compromised in previous security incidents and is no longer safe to use.</p>
    </div>
    """, unsafe_allow_html=True)
    
    with st.form("password_change_form"):
        st.subheader("Change Your Password")
        
        col1, col2 = st.columns(2)
        with col1:
            new_password = st.text_input("New Password", type="password", 
                                        help="Use 12+ characters with uppercase, lowercase, numbers, and symbols")
            st.caption("Password requirements:")
            st.caption("- At least 12 characters")
            st.caption("- Uppercase and lowercase letters")
            st.caption("- At least one number")
            st.caption("- At least one special character")
        
        with col2:
            confirm_password = st.text_input("Confirm New Password", type="password")
            st.caption("Password strength:")
            if new_password:
                is_strong, msg = is_strong_password(new_password)
                if is_strong:
                    st.success("✅ Password meets strength requirements")
                else:
                    st.error(f"❌ {msg}")
            
        submitted = st.form_submit_button("Change Password")
        
        if submitted:
            if new_password != confirm_password:
                st.error("Passwords do not match!")
            else:
                success, message = firebase_change_password(new_password)
                if success:
                    st.success(message)
                    st.session_state.password_breach_warning = False
                    st.rerun()
                else:
                    st.error(message)

def save_user_data_to_firestore(user_id):
    """Save all user data to Firestore"""
    if db is None:
        st.warning("Database not available. Data will be saved locally for this session only.")
        return False
    
    try:
        user_ref = db.collection(USER_DATA_COLLECTION).document(user_id)
        
        # Save profile and goals
        user_ref.set({
            PROFILE_DOCUMENT: {
                **st.session_state.user_profile,
                "email": st.session_state.user_email  # Add email to profile
            },
            GOALS_DOCUMENT: st.session_state.daily_goals
        })
        
        # Save food diary to subcollection
        food_diary_ref = user_ref.collection(FOOD_DIARY_SUBCOLLECTION)
        # Clear existing data
        docs = food_diary_ref.stream()
        for doc in docs:
            doc.reference.delete()
        # Add new data
        for _, row in st.session_state.food_diary.iterrows():
            food_diary_ref.add(row.to_dict())
        
        # Save exercise log to subcollection
        exercise_log_ref = user_ref.collection(EXERCISE_LOG_SUBCOLLECTION)
        docs = exercise_log_ref.stream()
        for doc in docs:
            doc.reference.delete()
        for _, row in st.session_state.exercise_log.iterrows():
            exercise_log_ref.add(row.to_dict())
        
        # Save weight log to subcollection
        weight_log_ref = user_ref.collection(WEIGHT_LOG_SUBCOLLECTION)
        docs = weight_log_ref.stream()
        for doc in docs:
            doc.reference.delete()
        for _, row in st.session_state.weight_log.iterrows():
            weight_log_ref.add(row.to_dict())
        
        # Save water log to subcollection
        water_log_ref = user_ref.collection(WATER_LOG_SUBCOLLECTION)
        docs = water_log_ref.stream()
        for doc in docs:
            doc.reference.delete()
        for _, row in st.session_state.water_log.iterrows():
            water_log_ref.add(row.to_dict())
        
        return True
    except Exception as e:
        st.error(f"Failed to save data: {e}")
        return False

def load_user_data_from_firestore(user_id):
    """Load all user data from Firestore"""
    if db is None:
        return False
    
    try:
        user_ref = db.collection(USER_DATA_COLLECTION).document(user_id)
        
        # Load profile and goals
        user_doc = user_ref.get()
        if user_doc.exists:
            user_data = user_doc.to_dict()
            st.session_state.user_profile = user_data.get(PROFILE_DOCUMENT, st.session_state.user_profile)
            if "email" in st.session_state.user_profile:
                st.session_state.user_email = st.session_state.user_profile["email"]
            st.session_state.daily_goals = user_data.get(GOALS_DOCUMENT, st.session_state.daily_goals)
        
        # Load food diary
        food_diary_ref = user_ref.collection(FOOD_DIARY_SUBCOLLECTION)
        food_docs = food_diary_ref.stream()
        food_data = [doc.to_dict() for doc in food_docs]
        if food_data:
            st.session_state.food_diary = pd.DataFrame(food_data, columns=FOOD_DIARY_COLS)
        else:
            st.session_state.food_diary = pd.DataFrame(columns=FOOD_DIARY_COLS)
        
        # Load exercise log
        exercise_log_ref = user_ref.collection(EXERCISE_LOG_SUBCOLLECTION)
        exercise_docs = exercise_log_ref.stream()
        exercise_data = [doc.to_dict() for doc in exercise_docs]
        if exercise_data:
            st.session_state.exercise_log = pd.DataFrame(exercise_data, columns=EXERCISE_LOG_COLS)
        else:
            st.session_state.exercise_log = pd.DataFrame(columns=EXERCISE_LOG_COLS)
        
        # Load weight log
        weight_log_ref = user_ref.collection(WEIGHT_LOG_SUBCOLLECTION)
        weight_docs = weight_log_ref.stream()
        weight_data = [doc.to_dict() for doc in weight_docs]
        if weight_data:
            st.session_state.weight_log = pd.DataFrame(weight_data, columns=WEIGHT_LOG_COLS)
        else:
            st.session_state.weight_log = pd.DataFrame(columns=WEIGHT_LOG_COLS)
        
        # Load water log
        water_log_ref = user_ref.collection(WATER_LOG_SUBCOLLECTION)
        water_docs = water_log_ref.stream()
        water_data = [doc.to_dict() for doc in water_docs]
        if water_data:
            st.session_state.water_log = pd.DataFrame(water_data, columns=WATER_LOG_COLS)
        else:
            st.session_state.water_log = pd.DataFrame(columns=WATER_LOG_COLS)
        
        return True
    except Exception as e:
        st.error(f"Failed to load data: {e}")
        return False

# ========================= UTILITY FUNCTIONS =========================

def fetch_food_from_openfoodfacts(query, limit=10):
    """Fetch food data from Open Food Facts API"""
    try:
        url = f"https://world.openfoodfacts.org/cgi/search.pl"
        params = {
            'search_terms': query,
            'search_simple': 1,
            'action': 'process',
            'json': 1,
            'page_size': limit
        }
        response = requests.get(url, params=params, timeout=5)
        if response.status_code == 200:
            data = response.json()
            foods = []
            for product in data.get('products', []):
                if product.get('product_name') and product.get('nutriments', {}):
                    nutriments = product['nutriments']
                    foods.append({
                        'name': product.get('product_name', 'Unknown'),
                        'brand': product.get('brands', ''),
                        'calories': nutriments.get('energy-kcal_100g', 0) or 0,
                        'protein': nutriments.get('proteins_100g', 0) or 0,
                        'carbs': nutriments.get('carbohydrates_100g', 0) or 0,
                        'fat': nutriments.get('fat_100g', 0) or 0,
                        'fiber': nutriments.get('fiber_100g', 0) or 0,
                        'sodium': nutriments.get('sodium_100g', 0) or 0,
                        'serving_size': '100g',
                        'source': 'Open Food Facts'
                    })
            return foods
    except Exception as e:
        st.error(f"Error fetching from Open Food Facts: {e}")
    return []

def fetch_food_from_usda(query, api_key="DEMO_KEY"):
    """Fetch food data from USDA FoodData Central API"""
    try:
        url = f"https://api.nal.usda.gov/fdc/v1/foods/search"
        params = {
            'query': query,
            'api_key': api_key,
            'limit': 10
        }
        response = requests.get(url, params=params, timeout=5)
        if response.status_code == 200:
            data = response.json()
            foods = []
            for food in data.get('foods', []):
                nutrients = {n['nutrientName']: n.get('value', 0) 
                           for n in food.get('foodNutrients', [])}
                foods.append({
                    'name': food.get('description', 'Unknown'),
                    'brand': food.get('brandOwner', ''),
                    'calories': nutrients.get('Energy', 0),
                    'protein': nutrients.get('Protein', 0),
                    'carbs': nutrients.get('Carbohydrate, by difference', 0),
                    'fat': nutrients.get('Total lipid (fat)', 0),
                    'fiber': nutrients.get('Fiber, total dietary', 0),
                    'sodium': nutrients.get('Sodium, Na', 0),
                    'serving_size': '100g',
                    'source': 'USDA'
                })
            return foods
    except Exception as e:
        pass  # Silently fail for DEMO_KEY rate limits
    return []

def calculate_calories_burned(activity, duration_min, weight_kg):
    """Calculate calories burned based on activity and duration"""
    # MET values for different activities
    met_values = {
        'Walking (slow)': 2.5,
        'Walking (moderate)': 3.5,
        'Walking (fast)': 4.5,
        'Running (slow)': 6.0,
        'Running (moderate)': 8.0,
        'Running (fast)': 11.0,
        'Cycling (light)': 4.0,
        'Cycling (moderate)': 6.0,
        'Cycling (intense)': 10.0,
        'Swimming': 6.0,
        'Yoga': 2.5,
        'Weight Training': 3.5,
        'HIIT': 8.0,
        'Dancing': 4.5,
        'Sports (moderate)': 6.0,
        'Sports (intense)': 8.0,
        'Household chores': 3.0,
        'Gardening': 4.0
    }
    
    met = met_values.get(activity, 3.5)
    calories = (met * weight_kg * duration_min) / 60
    return round(calories)

def calculate_bmr(weight_kg, height_cm, age, gender):
    """Calculate Basal Metabolic Rate using Mifflin-St Jeor equation"""
    if gender == "Male":
        bmr = (10 * weight_kg) + (6.25 * height_cm) - (5 * age) + 5
    else:
        bmr = (10 * weight_kg) + (6.25 * height_cm) - (5 * age) - 161
    return bmr

def calculate_tdee(bmr, activity_level):
    """Calculate Total Daily Energy Expenditure"""
    activity_multipliers = {
        'Sedentary': 1.2,
        'Lightly Active': 1.375,
        'Moderately Active': 1.55,
        'Very Active': 1.725,
        'Extra Active': 1.9
    }
    return bmr * activity_multipliers.get(activity_level, 1.2)

def calculate_bmi(weight_kg, height_cm):
    """Calculate BMI"""
    if height_cm <= 0:
        return None
    height_m = height_cm / 100
    return weight_kg / (height_m ** 2)

def get_bmi_category(bmi):
    """Get BMI category"""
    if bmi < 18.5:
        return "Underweight", "🔵"
    elif bmi < 25:
        return "Normal weight", "🟢"
    elif bmi < 30:
        return "Overweight", "🟡"
    else:
        return "Obese", "🔴"

# ========================= SESSION STATE INITIALIZATION =========================

# Initialize authentication state
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'user_email' not in st.session_state:
    st.session_state.user_email = None
if 'user_id' not in st.session_state:
    st.session_state.user_id = None
if 'password_breach_warning' not in st.session_state:
    st.session_state.password_breach_warning = False
if 'id_token' not in st.session_state:
    st.session_state.id_token = None
if 'refresh_token' not in st.session_state:
    st.session_state.refresh_token = None

# Initialize data state
if 'food_diary' not in st.session_state:
    st.session_state.food_diary = pd.DataFrame(columns=FOOD_DIARY_COLS)

if 'exercise_log' not in st.session_state:
    st.session_state.exercise_log = pd.DataFrame(columns=EXERCISE_LOG_COLS)

if 'weight_log' not in st.session_state:
    st.session_state.weight_log = pd.DataFrame(columns=WEIGHT_LOG_COLS)

if 'water_log' not in st.session_state:
    st.session_state.water_log = pd.DataFrame(columns=WATER_LOG_COLS)

if 'user_profile' not in st.session_state:
    st.session_state.user_profile = {
        'name': '',  # Added name field
        'weight_kg': 70,
        'height_cm': 175,
        'age': 25,
        'gender': 'Male',
        'activity_level': 'Moderately Active',
        'goal': 'Maintain Weight'
    }

if 'daily_goals' not in st.session_state:
    st.session_state.daily_goals = {
        'calories': 2000,
        'protein': 75,
        'carbs': 250,
        'fat': 65,
        'fiber': 25,
        'water': 8
    }

# ========================= SIDEBAR =========================

# Sidebar logo
st.sidebar.image("logoo.png", width=270)
st.sidebar.markdown("---")

# Authentication section
if not st.session_state.authenticated:
    st.sidebar.subheader("🔐 Sign In")
    
    # Authentication tabs
    tab_login, tab_register, tab_reset = st.sidebar.tabs(["Login", "Register", "Reset Password"])
    
    with tab_login:
        login_email = st.text_input("Email", key="login_email")
        login_password = st.text_input("Password", type="password", key="login_password")
        
        if st.button("Sign In", key="login_btn"):
            with st.spinner("Signing in..."):
                user = firebase_sign_in(login_email, login_password)
                if user:
                    st.session_state.authenticated = True
                    st.session_state.user_email = user["email"]
                    st.session_state.user_id = user["id"]
                    
                    # Load user data from Firestore
                    if load_user_data_from_firestore(st.session_state.user_id):
                        st.sidebar.success("Welcome back! Your data has been loaded.")
                    else:
                        st.sidebar.info("Welcome! This is your first time using FitVerse.")
                    
                    time.sleep(1)
                    st.rerun()
    
    with tab_register:
        name = st.text_input("Full Name")
        register_email = st.text_input("Email", key="register_email")
        register_password = st.text_input("Password", type="password", key="register_password")
        register_confirm = st.text_input("Confirm Password", type="password", key="register_confirm")
        
        if st.button("Create Account", key="register_btn"):
            if register_password != register_confirm:
                st.sidebar.error("Passwords do not match")
            elif not register_email or not register_password:
                st.sidebar.error("Please enter email and password")
            else:
                with st.spinner("Creating account..."):
                    user = firebase_sign_up(register_email, register_password)
                    if user:
                        # Store name in user profile
                        st.session_state.user_profile['name'] = name
                        
                        st.session_state.authenticated = True
                        st.session_state.user_email = user["email"]
                        st.session_state.user_id = user["id"]
                        
                        # Save initial profile to Firestore
                        save_user_data_to_firestore(st.session_state.user_id)
                        
                        st.sidebar.success("Account created successfully!")
                        time.sleep(1)
                        st.rerun()
    
    with tab_reset:
        reset_email = st.text_input("Enter your email", key="reset_email")
        if st.button("Send Reset Link", key="reset_btn"):
            if reset_email:
                success, message = firebase_reset_password(reset_email)
                if success:
                    st.sidebar.success(message)
                else:
                    st.sidebar.error(message)
            else:
                st.sidebar.error("Please enter your email address")   
else:
    # Navigation - Added "👤 My Profile" to the options
    page = st.sidebar.selectbox(
        "Navigate to",
        ["📊 Dashboard", "🍽️ Food Log", "💪 Exercise Log", 
         "📈 Progress Tracking", "⚖️ BMI & Goals", "👤 My Profile", "📖 User Guide"]
    )
    
    st.sidebar.markdown("---")
    st.sidebar.subheader("⚡ Quick Stats")
    today = date.today()
    today_str = str(today)

    # Calculate today's totals
    today_food = st.session_state.food_diary[st.session_state.food_diary['date'] == today_str]
    today_exercise = st.session_state.exercise_log[st.session_state.exercise_log['date'] == today_str]
    today_water = st.session_state.water_log[st.session_state.water_log['date'] == today_str]

    calories_consumed = today_food['calories'].sum() if not today_food.empty else 0
    calories_burned = today_exercise['calories_burned'].sum() if not today_exercise.empty else 0
    net_calories = calories_consumed - calories_burned
    water_glasses = today_water['glasses'].sum() if 'glasses' in today_water.columns and not today_water.empty else 0

    st.sidebar.metric("Net Calories Today", f"{net_calories:.0f}")
    st.sidebar.metric("Water (glasses)", f"{water_glasses:.0f}")
    
    # Add separator before save/sign out section
    st.sidebar.markdown("---")
    
    # Save and sign out section at bottom
    col1, col2 = st.sidebar.columns([2, 1])
    with col1:
        if st.button("💾 Save to Cloud"):
            with st.spinner("Saving your data..."):
                if save_user_data_to_firestore(st.session_state.user_id):
                    st.success("✅ Data saved!")
                    time.sleep(1)
                else:
                    st.error("❌ Save failed")
    
    with col2:
        # Auto-save every 5 minutes (simplified indicator)
        if 'last_autosave' not in st.session_state:
            st.session_state.last_autosave = time.time()
        
        if time.time() - st.session_state.last_autosave > 300:  # 5 minutes
            if save_user_data_to_firestore(st.session_state.user_id):
                st.session_state.last_autosave = time.time()
                st.write("🔄 Auto-saved")
    
    # Sign out button at very bottom
    if st.sidebar.button("🚪 Sign Out"):
        # Save data before signing out
        save_user_data_to_firestore(st.session_state.user_id)
        
        # Clear session state
        st.session_state.authenticated = False
        st.session_state.user_email = None
        st.session_state.user_id = None
        st.session_state.password_breach_warning = False
        st.rerun()

# Final separator
st.sidebar.markdown("---")

# Set page for unauthenticated users
if not st.session_state.authenticated:
    page = "🔐 Login Required"

# ========================= MAIN CONTENT =========================

# Show security warning if password is breached
if st.session_state.get("password_breach_warning", False):
    show_password_security_warning()
    st.stop()  # Block app access until password is changed

if not st.session_state.authenticated:
    # Modern dark theme UI with black, grey, and white
    st.markdown("""
    <style>
        .dark-theme {
            background-color: #0f1114;
            color: #ffffff;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }
        .hero {
            background: linear-gradient(135deg, #1a1c22 0%, #0f1114 100%);
            border-radius: 16px;
            padding: 3rem 2rem;
            color: white;
            text-align: center;
            margin-bottom: 2rem;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5);
            border: 1px solid #2a2e35;
        }
        .hero-title {
            font-size: 3.5rem;
            font-weight: 800;
            margin-bottom: 0.5rem;
            background: linear-gradient(135deg, #ffffff 0%, #a0aec0 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            text-shadow: 0 2px 4px rgba(0,0,0,0.2);
        }
        .hero-subtitle {
            font-size: 1.5rem;
            font-weight: 400;
            margin-bottom: 1.5rem;
            opacity: 0.8;
            color: #cbd5e0;
        }
        .feature-card {
            background: #1a1c22;
            border-radius: 16px;
            padding: 1.5rem;
            box-shadow: 0 6px 20px rgba(0,0,0,0.3);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
            height: 100%;
            border: 1px solid #2a2e35;
        }
        .feature-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 12px 30px rgba(0,0,0,0.4);
            border-color: #4a5568;
        }
        .feature-icon {
            font-size: 2.5rem;
            margin-bottom: 1rem;
            color: #718096;
        }
        .feature-title {
            font-size: 1.4rem;
            font-weight: 700;
            margin-bottom: 0.8rem;
            color: #e2e8f0;
        }
        .feature-list {
            text-align: left;
            padding-left: 1.5rem;
            color: #a0aec0;
        }
        .feature-list li {
            margin-bottom: 0.6rem;
        }
        .security-section {
            background: #1a1c22;
            border-radius: 16px;
            padding: 2rem;
            margin: 2rem 0;
            border-left: 4px solid #4a5568;
            box-shadow: 0 6px 20px rgba(0,0,0,0.3);
            border: 1px solid #2a2e35;
        }
        .cta-button {
            background: linear-gradient(135deg, #2d3748 0%, #1a202c 100%);
            color: #e2e8f0;
            border: 1px solid #4a5568;
            padding: 0.8rem 2.5rem;
            border-radius: 50px;
            font-weight: 700;
            font-size: 1.1rem;
            cursor: pointer;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(0,0,0,0.3);
            margin-top: 1rem;
            display: inline-block;
        }
        .cta-button:hover {
            transform: translateY(-3px);
            box-shadow: 0 8px 25px rgba(0,0,0,0.4);
            background: linear-gradient(135deg, #2d3748 0%, #2d3748 100%);
            color: #ffffff;
            text-decoration: none;
        }
        .stats-container {
            background: #1a1c22;
            border-radius: 16px;
            padding: 1.5rem;
            box-shadow: 0 6px 20px rgba(0,0,0,0.3);
            border: 1px solid #2a2e35;
            text-align: center;
        }
        .stats-number {
            font-size: 2.5rem;
            font-weight: 800;
            background: linear-gradient(135deg, #ffffff 0%, #a0aec0 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .stats-text {
            font-size: 1.1rem;
            color: #a0aec0;
        }
        .step-card {
            background: #1a1c22;
            border-radius: 16px;
            padding: 1.5rem;
            box-shadow: 0 6px 20px rgba(0,0,0,0.3);
            height: 100%;
            border: 1px solid #2a2e35;
            text-align: center;
        }
        .step-icon {
            font-size: 2.5rem;
            margin-bottom: 1rem;
            color: #718096;
        }
        .step-title {
            font-size: 1.25rem;
            font-weight: 700;
            margin-bottom: 0.5rem;
            color: #e2e8f0;
        }
        .step-desc {
            color: #a0aec0;
        }
        .divider {
            height: 1px;
            background: linear-gradient(90deg, transparent, #2d3748, transparent);
            margin: 2rem 0;
        }
        .final-cta {
            text-align: center;
            margin: 3rem 0;
        }
        .section-title {
            font-size: 2rem;
            font-weight: 700;
            margin-bottom: 1.5rem;
            background: linear-gradient(135deg, #ffffff 0%, #a0aec0 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
    </style>
    """, unsafe_allow_html=True)
    
    # Hero section with dark theme
    st.markdown("""
    <div class="hero">
        <div class="hero-title">FITVERSE</div>
        <div class="hero-subtitle">Your Complete Fitness Tracking Companion</div>
        <p style="font-size:1.1rem; max-width:700px; margin:0 auto 1.5rem; color:#a0aec0;">
            Transform your fitness journey with advanced tracking and personalized insights
        </p>
        <a href="#features" class="cta-button">EXPLORE FEATURES</a>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown('<a name="features"></a>', unsafe_allow_html=True)
    
    # Features showcase with modern dark cards
    st.markdown('<div class="section-title">Why Choose FitVerse?</div>', unsafe_allow_html=True)
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("""
        <div class="feature-card">
            <div class="feature-icon">🍽️</div>
            <div class="feature-title">Smart Food Logging</div>
            <ul class="feature-list">
                <li>Search thousands of foods</li>
                <li>Automatic nutrition calculation</li>
                <li>Meal planning and tracking</li>
                <li>Custom food creation</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div class="feature-card">
            <div class="feature-icon">💪</div>
            <div class="feature-title">Exercise Tracking</div>
            <ul class="feature-list">
                <li>Log various activities</li>
                <li>Calculate calories burned</li>
                <li>Track workout intensity</li>
                <li>Exercise library with tips</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown("""
        <div class="feature-card">
            <div class="feature-icon">📈</div>
            <div class="feature-title">Progress Analytics</div>
            <ul class="feature-list">
                <li>Weight tracking charts</li>
                <li>Macronutrient analysis</li>
                <li>Goal achievement insights</li>
                <li>Water intake monitoring</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
    
    # Stats row with dark theme
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Transform Your Fitness Journey</div>', unsafe_allow_html=True)
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("""
        <div class="stats-container">
            <div class="stats-number">95%</div>
            <div class="stats-text">Users achieve fitness goals faster</div>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown("""
        <div class="stats-container">
            <div class="stats-number">100,000+</div>
            <div class="stats-text">Foods in our nutrition database</div>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        st.markdown("""
        <div class="stats-container">
            <div class="stats-number">24/7</div>
            <div class="stats-text">Access to your fitness data</div>
        </div>
        """, unsafe_allow_html=True)
    
    # How it works section with dark theme
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">How FitVerse Works</div>', unsafe_allow_html=True)
    steps = [
        ("1. Sign Up", "Create your personalized account in seconds", "📝"),
        ("2. Set Goals", "Define your fitness objectives and targets", "🎯"),
        ("3. Track Progress", "Log meals, exercises, and measurements", "📊"),
        ("4. Achieve Results", "Gain insights and reach your fitness goals", "🏆")
    ]
    
    cols = st.columns(4)
    for i, (title, desc, icon) in enumerate(steps):
        with cols[i]:
            st.markdown(f"""
            <div class="step-card">
                <div class="step-icon">{icon}</div>
                <div class="step-title">{title}</div>
                <div class="step-desc">{desc}</div>
            </div>
            """, unsafe_allow_html=True)
    
    # Security section with dark theme
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Your Security is Our Priority</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="security-section">
        <div style="display:flex; align-items:center; gap:1.5rem">
            <div style="flex:1">
                <h3 style="color:#e2e8f0; margin-top:0">Enterprise-grade Security</h3>
                <ul style="color:#a0aec0; padding-left:1.5rem">
                    <li>Military-grade AES-256 encryption</li>
                    <li>Regular security audits and penetration testing</li>
                    <li>Breached password protection with HIBP integration</li>
                    <li>Secure cloud storage with Google Firebase</li>
                    <li>GDPR-compliant data handling</li>
                </ul>
            </div>
            <div style="flex:1; text-align:center">
                <div style="font-size:5rem; line-height:1; color:#4a5568">🔐</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Final CTA with dark theme
    st.markdown("""
    <div class="final-cta">
        <div class="section-title">Ready to Transform Your Fitness Journey?</div>
        <p style="font-size:1.2rem; margin-bottom:1.5rem; color:#a0aec0">
            Join thousands of users achieving their fitness goals with FitVerse
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    st.stop()  # Stop execution here if not authenticated

# ========================= AUTHENTICATED PAGES =========================

if page == "📊 Dashboard":
    # Get display name (use name if available, otherwise use email prefix)
    name = st.session_state.user_profile.get('name', '')
    display_name = name if name else st.session_state.user_email.split('@')[0]
    
    st.title("FitVerse - Complete Fitness Tracker")
    st.markdown(f"### Welcome back, {display_name}! Today is {today.strftime('%B %d, %Y')}")
    
    # Top metrics row
    col1, col2, col3, col4 = st.columns(4)
    
    # Convert calories to numeric before calculation
    if not st.session_state.food_diary.empty:
        st.session_state.food_diary['calories'] = pd.to_numeric(
            st.session_state.food_diary['calories'], errors='coerce'
        )
    
    calories_consumed = today_food['calories'].sum() if not today_food.empty else 0
    progress = (calories_consumed / st.session_state.daily_goals['calories']) * 100
    
    with col1:
        st.metric(
            "Calories Consumed",
            f"{calories_consumed:.0f}",
            f"{progress:.1f}% of goal"
        )
    
    with col2:
        st.metric(
            "Calories Burned",
            f"{calories_burned:.0f}",
            "From exercise"
        )
    
    with col3:
        remaining = st.session_state.daily_goals['calories'] - net_calories
        st.metric(
            "Calories Remaining",
            f"{remaining:.0f}",
            "To reach goal"
        )
    
    with col4:
        st.metric(
            "Water Intake",
            f"{water_glasses} glasses",
            f"{(water_glasses/8)*100:.0f}% of goal"
        )
    
    st.markdown("---")
    
    # Progress rings
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("📈 Today's Progress")
        
        # Create progress chart
        fig = go.Figure()
        
        # Calories ring
        fig.add_trace(go.Indicator(
            mode = "gauge+number+delta",
            value = calories_consumed,
            title = {'text': "Calories"},
            delta = {'reference': st.session_state.daily_goals['calories']},
            gauge = {'axis': {'range': [None, st.session_state.daily_goals['calories'] * 1.2]},
                    'bar': {'color': "darkblue"},
                    'steps': [
                        {'range': [0, st.session_state.daily_goals['calories'] * 0.8], 'color': "lightgray"},
                        {'range': [st.session_state.daily_goals['calories'] * 0.8, 
                                 st.session_state.daily_goals['calories']], 'color': "gray"}],
                    'threshold': {'line': {'color': "red", 'width': 4}, 
                                'thickness': 0.75, 
                                'value': st.session_state.daily_goals['calories']}}))
        
        fig.update_layout(height=300)
        st.plotly_chart(fig, use_container_width=True)
        
        # Macros breakdown
        st.subheader("Macronutrients Breakdown")
        if not today_food.empty:
            # Convert columns to numeric
            numeric_cols = ['protein', 'carbs', 'fat']
            today_food[numeric_cols] = today_food[numeric_cols].apply(
                pd.to_numeric, errors='coerce'
            )
            
            protein_total = today_food['protein'].sum()
            carbs_total = today_food['carbs'].sum()
            fat_total = today_food['fat'].sum()
            
            macro_data = pd.DataFrame({
                'Macro': ['Protein', 'Carbs', 'Fat'],
                'Grams': [protein_total, carbs_total, fat_total],
                'Goal': [st.session_state.daily_goals['protein'],
                        st.session_state.daily_goals['carbs'],
                        st.session_state.daily_goals['fat']]
            })
            
            fig_macro = px.bar(macro_data, x='Macro', y=['Grams', 'Goal'], 
                             barmode='group', color_discrete_map={'Grams': '#3498db', 'Goal': '#95a5a6'})
            fig_macro.update_layout(height=300)
            st.plotly_chart(fig_macro, use_container_width=True)
        else:
            st.info("No food logged today yet")
    
    with col2:
        st.subheader("🎯 Daily Goals")
        
        goals_df = pd.DataFrame({
            'Goal': ['Calories', 'Protein (g)', 'Carbs (g)', 'Fat (g)', 'Water (glasses)'],
            'Target': [st.session_state.daily_goals['calories'],
                      st.session_state.daily_goals['protein'],
                      st.session_state.daily_goals['carbs'],
                      st.session_state.daily_goals['fat'],
                      st.session_state.daily_goals['water']],
            'Current': [calories_consumed,
                       today_food['protein'].sum() if not today_food.empty else 0,
                       today_food['carbs'].sum() if not today_food.empty else 0,
                       today_food['fat'].sum() if not today_food.empty else 0,
                       water_glasses]
        })
        goals_df['Progress %'] = (goals_df['Current'] / goals_df['Target'] * 100).round(1)
        
        for _, row in goals_df.iterrows():
            progress = min(row['Progress %'], 100)
            color = 'green' if progress >= 80 else 'orange' if progress >= 50 else 'red'
            st.progress(progress / 100)
            st.write(f"**{row['Goal']}**: {row['Current']:.0f}/{row['Target']:.0f} ({row['Progress %']:.1f}%)")
    
    st.markdown("---")
    
    # Recent meals and exercises
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Recent Meals")
        if not today_food.empty:
            recent_meals = today_food[['meal', 'food_name', 'calories']].tail(5)
            st.dataframe(recent_meals, hide_index=True)
        else:
            st.info("No meals logged today")
    
    with col2:
        st.subheader("Recent Exercises")
        if not today_exercise.empty:
            recent_ex = today_exercise[['activity', 'duration_min', 'calories_burned']].tail(5)
            st.dataframe(recent_ex, hide_index=True)
        else:
            st.info("No exercises logged today")

elif page == "🍽️ Food Log":
    st.title("Food Log")
    
    tab1, tab2, tab3 = st.tabs(["Search & Add Food", "Today's Log", "Quick Add"])
    
    with tab1:
        st.subheader("Search Food Database")
        
        col1, col2 = st.columns([3, 1])
        with col1:
            search_query = st.text_input("Search for food (e.g., 'biryani', 'apple')")
        with col2:
            search_source = st.selectbox("Source", ["Open Food Facts", "USDA", "Both"])
        
        if search_query:
            with st.spinner("Searching food databases..."):
                results = []
                
                if search_source in ["Open Food Facts", "Both"]:
                    off_results = fetch_food_from_openfoodfacts(search_query)
                    results.extend(off_results)
                
                if search_source in ["USDA", "Both"]:
                    usda_results = fetch_food_from_usda(search_query)
                    results.extend(usda_results)
                
                if results:
                    st.success(f"Found {len(results)} results")
                    
                    # Display results
                    for idx, food in enumerate(results[:10]):
                        with st.expander(f"{food['name']} {f'({food['brand']})' if food['brand'] else ''} - {food['source']}"):
                            col1, col2, col3 = st.columns([2, 1, 1])
                            
                            with col1:
                                st.write(f"**Calories:** {food['calories']} kcal")
                                st.write(f"**Protein:** {food['protein']}g | **Carbs:** {food['carbs']}g | **Fat:** {food['fat']}g")
                            
                            with col2:
                                meal_type = st.selectbox(
                                    f"Meal_{idx}", 
                                    ["Breakfast", "Lunch", "Dinner", "Snack"],
                                    key=f"meal_{idx}"
                                )
                                
                                quantity = st.number_input(
                                    f"Quantity_{idx}",
                                    min_value=1,  # integer minimum
                                    value=1,      # integer default
                                    step=1,       # step in integers
                                    key=f"qty_{idx}"
                                )
                            
                            with col3:
                                if st.button(f"Add to diary", key=f"add_{idx}"):
                                    new_entry = pd.DataFrame([{
                                        'date': str(date.today()),
                                        'meal': meal_type,
                                        'food_name': food['name'],
                                        'brand': food['brand'],
                                        'calories': food['calories'] * quantity,
                                        'protein': food['protein'] * quantity,
                                        'carbs': food['carbs'] * quantity,
                                        'fat': food['fat'] * quantity,
                                        'fiber': food.get('fiber', 0) * quantity,
                                        'quantity': quantity,
                                        'serving_size': food['serving_size']
                                    }])
                                    st.session_state.food_diary = pd.concat([st.session_state.food_diary, new_entry], ignore_index=True)
                                    st.success(f"Added {food['name']} to {meal_type}!")
                                    st.rerun()
                else:
                    st.warning("No results found. Try a different search term.")
    
    with tab2:
        st.subheader("Today's Food Log")
        
        today_food = st.session_state.food_diary[st.session_state.food_diary['date'] == str(date.today())]
        
        if not today_food.empty:
            # Convert columns to numeric
            numeric_cols = ['calories', 'protein', 'carbs', 'fat', 'fiber']
            today_food[numeric_cols] = today_food[numeric_cols].apply(
                pd.to_numeric, errors='coerce'
            )
            
            # Group by meal
            for meal in ['Breakfast', 'Lunch', 'Dinner', 'Snack']:
                meal_data = today_food[today_food['meal'] == meal]
                if not meal_data.empty:
                    st.write(f"### {meal}")
                    display_cols = ['food_name', 'quantity', 'calories', 'protein', 'carbs', 'fat']
                    st.dataframe(meal_data[display_cols], hide_index=True)
                    st.write(f"**{meal} Total:** {meal_data['calories'].sum():.0f} kcal")
            
            st.markdown("---")
            st.subheader("Daily Totals")
            col1, col2, col3, col4 = st.columns(4)
            calories_sum = today_food['calories'].sum()
            protein_sum = today_food['protein'].sum()
            carbs_sum = today_food['carbs'].sum()
            fat_sum = today_food['fat'].sum()
            with col1:
                st.metric("Calories", f"{calories_sum:.0f}")
            with col2:
                st.metric("Protein", f"{protein_sum:.1f}g")
            with col3:
                st.metric("Carbs", f"{carbs_sum:.1f}g")
            with col4:
                st.metric("Fat", f"{fat_sum:.1f}g")
        else:
            st.info("No food logged today yet. Search and add foods from the 'Search & Add Food' tab.")
    
    with tab3:
        st.subheader("Quick Add Custom Food")
        
        col1, col2 = st.columns(2)
        
        with col1:
            food_name = st.text_input("Food name")
            meal_type = st.selectbox("Meal", ["Breakfast", "Lunch", "Dinner", "Snack"])
            serving_size = st.text_input("Serving size", value="1 serving")
        
        with col2:
            calories = st.number_input("Calories", min_value=0, value=100)
            protein = st.number_input("Protein (g)", min_value=0.0, value=0.0)
            carbs = st.number_input("Carbs (g)", min_value=0.0, value=0.0)
            fat = st.number_input("Fat (g)", min_value=0.0, value=0.0)
        
        if st.button("Add Custom Food"):
            if food_name:
                new_entry = pd.DataFrame([{
                    'date': str(date.today()),
                    'meal': meal_type,
                    'food_name': food_name,
                    'brand': 'Custom',
                    'calories': calories,
                    'protein': protein,
                    'carbs': carbs,
                    'fat': fat,
                    'fiber': 0,
                    'quantity': 1,
                    'serving_size': serving_size
                }])
                st.session_state.food_diary = pd.concat([st.session_state.food_diary, new_entry], ignore_index=True)
                st.success(f"Added {food_name} to {meal_type}!")
                st.rerun()
            else:
                st.error("Please enter a food name")

elif page == "💪 Exercise Log":
    st.title("Exercise Log")
    
    tab1, tab2, tab3 = st.tabs(["Log Exercise", "Today's Activities", "Exercise Library"])
    
    with tab1:
        st.subheader("Log Your Exercise")
        
        col1, col2 = st.columns(2)
        
        with col1:
            activity = st.selectbox("Activity", [
                'Walking (slow)', 'Walking (moderate)', 'Walking (fast)',
                'Running (slow)', 'Running (moderate)', 'Running (fast)',
                'Cycling (light)', 'Cycling (moderate)', 'Cycling (intense)',
                'Swimming', 'Yoga', 'Weight Training', 'HIIT',
                'Dancing', 'Sports (moderate)', 'Sports (intense)',
                'Household chores', 'Gardening'
            ])
            
            duration = st.number_input("Duration (minutes)", min_value=1, value=30, step=10)
            intensity = st.select_slider("Intensity", 
                options=['Light', 'Moderate', 'Intense', 'Very Intense'])
        
        with col2:
            weight = st.session_state.user_profile['weight_kg']
            calories_burned = calculate_calories_burned(activity, duration, weight)
            
            st.info(f"Estimated calories burned: **{calories_burned} kcal**")
            st.caption(f"Based on your weight: {weight} kg")
            
            if st.button("Log Exercise", type="primary"):
                new_exercise = pd.DataFrame([{
                    'date': str(date.today()),
                    'activity': activity,
                    'duration_min': duration,
                    'calories_burned': calories_burned,
                    'intensity': intensity
                }])
                st.session_state.exercise_log = pd.concat([st.session_state.exercise_log, new_exercise], ignore_index=True)
                st.success(f"Logged {activity} for {duration} minutes!")
                st.rerun()
    
    with tab2:
        st.subheader("Today's Exercise Log")
        
        today_exercise = st.session_state.exercise_log[st.session_state.exercise_log['date'] == str(date.today())]
        
        if not today_exercise.empty:
            st.dataframe(today_exercise[['activity', 'duration_min', 'intensity', 'calories_burned']], hide_index=True)
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Duration", f"{today_exercise['duration_min'].sum()} min")
            with col2:
                st.metric("Total Calories Burned", f"{today_exercise['calories_burned'].sum():.0f} kcal")
            with col3:
                st.metric("Activities Completed", f"{len(today_exercise)}")
            
            # Activity breakdown chart
            fig = px.pie(today_exercise, values='calories_burned', names='activity', 
                        title='Calories Burned by Activity')
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No exercises logged today. Start by logging an activity!")
    
    with tab3:
        st.subheader("Exercise Library & Tips")
        
        st.write("### 🏃 Cardio Exercises")
        cardio_tips = {
            "Running": "Great for cardiovascular health. Start slow and gradually increase pace.",
            "Cycling": "Low-impact exercise suitable for all fitness levels.",
            "Swimming": "Full-body workout that's easy on joints.",
            "HIIT": "High-intensity intervals boost metabolism for hours after workout."
        }
        for exercise, tip in cardio_tips.items():
            st.write(f"**{exercise}:** {tip}")
        
        st.write("### 💪 Strength Training")
        strength_tips = {
            "Weight Training": "Build muscle and increase metabolism. Focus on form over weight.",
            "Bodyweight Exercises": "No equipment needed. Perfect for home workouts.",
            "Resistance Bands": "Portable and versatile for full-body workouts."
        }
        for exercise, tip in strength_tips.items():
            st.write(f"**{exercise}:** {tip}")

elif page == "📈 Progress Tracking":
    st.title("Progress Tracking")
    
    tab1, tab2, tab3, tab4 = st.tabs(["Weight Progress", "Calorie Trends", "Macro Analysis", "Water Intake"])
    
    with tab1:
        st.subheader("Weight Tracking")
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            weight = st.number_input("Current Weight (kg)", min_value=30.0, value=70.0, step=0.5)
            if st.button("Log Weight"):
                new_weight = pd.DataFrame([{
                    'date': str(date.today()),
                    'weight_kg': weight
                }])
                st.session_state.weight_log = pd.concat([st.session_state.weight_log, new_weight], ignore_index=True)
                st.success(f"Weight logged: {weight} kg")
                st.rerun()
        
        with col2:
            if not st.session_state.weight_log.empty:
                # Convert weight to numeric
                st.session_state.weight_log['weight_kg'] = pd.to_numeric(
                    st.session_state.weight_log['weight_kg'], errors='coerce'
                )
                
                # Weight trend chart
                fig = px.line(st.session_state.weight_log, x='date', y='weight_kg', 
                            title='Weight Progress Over Time', markers=True)
                fig.update_layout(xaxis_title="Date", yaxis_title="Weight (kg)")
                st.plotly_chart(fig, use_container_width=True)
                
                # Statistics
                latest_weight = st.session_state.weight_log.iloc[-1]['weight_kg']
                first_weight = st.session_state.weight_log.iloc[0]['weight_kg']
                weight_change = latest_weight - first_weight
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Current Weight", f"{latest_weight:.1f} kg")
                with col2:
                    st.metric("Total Change", f"{weight_change:+.1f} kg")
                with col3:
                    st.metric("Starting Weight", f"{first_weight:.1f} kg")
            else:
                st.info("No weight data logged yet")
    
    with tab2:
        st.subheader("Calorie Trends")
        
        if not st.session_state.food_diary.empty:
            # Convert calories to numeric
            st.session_state.food_diary['calories'] = pd.to_numeric(
                st.session_state.food_diary['calories'], errors='coerce'
            )
            
            # Aggregate calories by date
            daily_calories = st.session_state.food_diary.groupby('date')['calories'].sum().reset_index()
            
            if not st.session_state.exercise_log.empty:
                # Convert calories_burned to numeric
                st.session_state.exercise_log['calories_burned'] = pd.to_numeric(
                    st.session_state.exercise_log['calories_burned'], errors='coerce'
                )
                daily_exercise = st.session_state.exercise_log.groupby('date')['calories_burned'].sum().reset_index()
                daily_data = pd.merge(daily_calories, daily_exercise, on='date', how='outer').fillna(0)
                daily_data['net_calories'] = daily_data['calories'] - daily_data['calories_burned']
            else:
                daily_data = daily_calories
                daily_data['calories_burned'] = 0
                daily_data['net_calories'] = daily_data['calories']
            
            # Calorie trend chart
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=daily_data['date'], y=daily_data['calories'],
                                    mode='lines+markers', name='Consumed',
                                    line=dict(color='blue', width=2)))
            fig.add_trace(go.Scatter(x=daily_data['date'], y=daily_data['calories_burned'],
                                    mode='lines+markers', name='Burned',
                                    line=dict(color='red', width=2)))
            fig.add_trace(go.Scatter(x=daily_data['date'], y=daily_data['net_calories'],
                                    mode='lines+markers', name='Net',
                                    line=dict(color='green', width=2)))
            
            fig.add_hline(y=st.session_state.daily_goals['calories'], 
                         line_dash="dash", line_color="gray",
                         annotation_text="Goal")
            
            fig.update_layout(title='Daily Calorie Trends',
                            xaxis_title='Date',
                            yaxis_title='Calories',
                            hovermode='x unified')
            st.plotly_chart(fig, use_container_width=True)
            
            # Statistics
            col1, col2, col3 = st.columns(3)
            with col1:
                avg_consumed = daily_data['calories'].mean()
                st.metric("Avg Daily Intake", f"{avg_consumed:.0f} kcal")
            with col2:
                avg_burned = daily_data['calories_burned'].mean()
                st.metric("Avg Daily Burn", f"{avg_burned:.0f} kcal")
            with col3:
                avg_net = daily_data['net_calories'].mean()
                st.metric("Avg Net Calories", f"{avg_net:.0f} kcal")
        else:
            st.info("No calorie data available yet")

    with tab3:
        st.subheader("Macronutrient Analysis")
        
        if not st.session_state.food_diary.empty:
            # Convert nutrient columns to numeric
            nutrient_cols = ['protein', 'carbs', 'fat']
            st.session_state.food_diary[nutrient_cols] = st.session_state.food_diary[nutrient_cols].apply(
                pd.to_numeric, errors='coerce'
            )
            
            # Date range selector
            date_range = st.date_input("Select date range", 
                                      value=(date.today() - timedelta(days=7), date.today()),
                                      max_value=date.today())
            
            if len(date_range) == 2:
                start_date, end_date = date_range
                mask = (pd.to_datetime(st.session_state.food_diary['date']).dt.date >= start_date) & \
                       (pd.to_datetime(st.session_state.food_diary['date']).dt.date <= end_date)
                filtered_data = st.session_state.food_diary[mask]
                
                if not filtered_data.empty:
                    # Daily macro trends
                    daily_macros = filtered_data.groupby('date')[['protein', 'carbs', 'fat']].sum().reset_index()
                    
                    fig = go.Figure()
                    fig.add_trace(go.Bar(x=daily_macros['date'], y=daily_macros['protein'],
                                       name='Protein', marker_color='indianred'))
                    fig.add_trace(go.Bar(x=daily_macros['date'], y=daily_macros['carbs'],
                                       name='Carbs', marker_color='lightsalmon'))
                    fig.add_trace(go.Bar(x=daily_macros['date'], y=daily_macros['fat'],
                                       name='Fat', marker_color='lightgreen'))
                    
                    fig.update_layout(title='Daily Macronutrient Distribution',
                                    xaxis_title='Date',
                                    yaxis_title='Grams',
                                    barmode='group')
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # Average macro distribution pie chart
                    avg_protein = filtered_data['protein'].sum()
                    avg_carbs = filtered_data['carbs'].sum()
                    avg_fat = filtered_data['fat'].sum()
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        fig_pie = go.Figure(data=[go.Pie(
                            labels=['Protein', 'Carbs', 'Fat'],
                            values=[avg_protein, avg_carbs, avg_fat],
                            hole=.3
                        )])
                        fig_pie.update_layout(title='Overall Macro Distribution')
                        st.plotly_chart(fig_pie, use_container_width=True)
                    
                    with col2:
                        st.write("### Macro Statistics")
                        total_days = len(daily_macros)
                        st.write(f"**Analysis Period:** {total_days} days")
                        st.write(f"**Avg Protein:** {avg_protein/total_days:.1f}g/day")
                        st.write(f"**Avg Carbs:** {avg_carbs/total_days:.1f}g/day")
                        st.write(f"**Avg Fat:** {avg_fat/total_days:.1f}g/day")
                        
                        # Calorie breakdown from macros
                        protein_cal = avg_protein * 4
                        carbs_cal = avg_carbs * 4
                        fat_cal = avg_fat * 9
                        total_cal = protein_cal + carbs_cal + fat_cal
                        
                        st.write("### Calorie Sources")
                        st.write(f"**From Protein:** {(protein_cal/total_cal*100):.1f}%")
                        st.write(f"**From Carbs:** {(carbs_cal/total_cal*100):.1f}%")
                        st.write(f"**From Fat:** {(fat_cal/total_cal*100):.1f}%")
                else:
                    st.info("No data in selected range")
        else:
            st.info("No food data available yet")
    
    with tab4:
        st.subheader("Water Intake Tracking")
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            water_input = st.number_input("Glasses of water", min_value=1, max_value=20, value=1)
            if st.button("Log Water"):
                new_water = pd.DataFrame([{
                    'date': str(date.today()),
                    'glasses': water_input
                }])
                st.session_state.water_log = pd.concat([st.session_state.water_log, new_water], ignore_index=True)
                st.success(f"Logged {water_input} glasses of water!")
                st.rerun()
            
            st.markdown("---")
            st.info("💧 **Tip:** Aim for 8 glasses (2 liters) of water daily")
        
        with col2:
            if not st.session_state.water_log.empty:
                # Convert glasses to numeric
                st.session_state.water_log['glasses'] = pd.to_numeric(
                    st.session_state.water_log['glasses'], errors='coerce'
                )
                
                # Water intake trend
                daily_water = st.session_state.water_log.groupby('date')['glasses'].sum().reset_index()
                
                fig = go.Figure()
                fig.add_trace(go.Bar(x=daily_water['date'], y=daily_water['glasses'],
                                   marker_color='lightblue'))
                fig.add_hline(y=8, line_dash="dash", line_color="blue",
                            annotation_text="Goal (8 glasses)")
                
                fig.update_layout(title='Daily Water Intake',
                                xaxis_title='Date',
                                yaxis_title='Glasses')
                st.plotly_chart(fig, use_container_width=True)
                
                # Statistics
                avg_water = daily_water['glasses'].mean()
                days_met_goal = len(daily_water[daily_water['glasses'] >= 8])
                total_days = len(daily_water)
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Average Daily", f"{avg_water:.1f} glasses")
                with col2:
                    st.metric("Goal Achievement", f"{days_met_goal}/{total_days} days")
                with col3:
                    achievement_rate = (days_met_goal/total_days*100) if total_days > 0 else 0
                    st.metric("Success Rate", f"{achievement_rate:.0f}%")
            else:
                st.info("No water intake data yet. Start logging your water consumption!")

elif page == "⚖️ BMI & Goals":
    st.title("BMI Calculator & Goal Setting")
    
    tab1, tab2, tab3 = st.tabs(["BMI Calculator", "Goal Setting", "Recommendations"])
    
    with tab1:
        st.subheader("Calculate Your BMI")
        
        col1, col2 = st.columns(2)
        
        with col1:
            weight = st.number_input("Weight (kg)", min_value=30.0, max_value=300.0, 
                                   value=float(st.session_state.user_profile['weight_kg']), step=0.5)
            height = st.number_input("Height (cm)", min_value=100.0, max_value=250.0, 
                                   value=float(st.session_state.user_profile['height_cm']), step=1.0)
            
            if st.button("Calculate BMI", type="primary"):
                bmi = calculate_bmi(weight, height)
                if bmi:
                    category, emoji = get_bmi_category(bmi)
                    
                    st.markdown("---")
                    col_a, col_b = st.columns(2)
                    with col_a:
                        st.metric("Your BMI", f"{bmi:.1f}")
                    with col_b:
                        st.metric("Category", f"{emoji} {category}")
                    
                    # BMI interpretation
                    if bmi < 18.5:
                        st.info("**Underweight:** Consider increasing caloric intake with nutrient-dense foods.")
                    elif bmi < 25:
                        st.success("**Normal weight:** Maintain your current healthy lifestyle!")
                    elif bmi < 30:
                        st.warning("**Overweight:** Consider a balanced diet and regular exercise.")
                    else:
                        st.error("**Obese:** Consult with a healthcare provider for a personalized plan.")
        
        with col2:
            # BMI Chart visualization
            fig = go.Figure()
            
            # BMI categories
            categories = ['Underweight', 'Normal', 'Overweight', 'Obese']
            ranges = [18.5, 25, 30, 40]
            colors = ['lightblue', 'lightgreen', 'yellow', 'red']
            
            # Create BMI scale
            for i, (cat, color) in enumerate(zip(categories, colors)):
                fig.add_trace(go.Bar(
                    x=[ranges[i] if i < len(ranges) else 40],
                    y=[cat],
                    orientation='h',
                    marker=dict(color=color),
                    showlegend=False,
                    hovertemplate=f'{cat}: BMI {ranges[i-1] if i > 0 else 0}-{ranges[i] if i < len(ranges) else "40+"}<extra></extra>'
                ))
            
            # Add user's BMI marker if calculated
            if 'bmi' in locals():
                fig.add_vline(x=bmi, line_dash="dash", line_color="black",
                            annotation_text=f"Your BMI: {bmi:.1f}")
            
            fig.update_layout(
                title="BMI Scale",
                xaxis_title="BMI Value",
                yaxis_title="Category",
                barmode='stack',
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # Ideal weight calculator
            st.write("### Ideal Weight Range")
            ideal_bmi_min = 18.5
            ideal_bmi_max = 24.9
            height_m = height / 100
            ideal_weight_min = ideal_bmi_min * (height_m ** 2)
            ideal_weight_max = ideal_bmi_max * (height_m ** 2)
            
            st.info(f"For your height ({height} cm), ideal weight range is: **{ideal_weight_min:.1f} - {ideal_weight_max:.1f} kg**")
    
    with tab2:
        st.subheader("Set Your Fitness Goals")
        
        st.write("### Current Daily Goals")
        calories = st.number_input("Calories", value=st.session_state.daily_goals['calories'], step=50)
        protein = st.number_input("Protein (g)", value=st.session_state.daily_goals['protein'], step=5)
        carbs = st.number_input("Carbs (g)", value=st.session_state.daily_goals['carbs'], step=10)
        fat = st.number_input("Fat (g)", value=st.session_state.daily_goals['fat'], step=5)
        fiber = st.number_input("Fiber (g)", value=st.session_state.daily_goals['fiber'], step=5)
        water = st.number_input("Water (glasses)", value=st.session_state.daily_goals['water'], step=1)
        
        if st.button("Save Custom Goals"):
            st.session_state.daily_goals.update({
                'calories': calories,
                'protein': protein,
                'carbs': carbs,
                'fat': fat,
                'fiber': fiber,
                'water': water
            })
            st.success("Custom goals saved!")
            st.rerun()

    with tab3:
        st.subheader("Personalized Recommendations")
        
        # Get user's BMI
        bmi = calculate_bmi(
            st.session_state.user_profile['weight_kg'],
            st.session_state.user_profile['height_cm']
        )
        
        if bmi:
            category, _ = get_bmi_category(bmi)
            st.write(f"### Based on your BMI: {bmi:.1f} ({category})")
            
            if category == "Underweight":
                st.info("""
                **Nutrition Recommendations:**
                - Increase calorie intake with nutrient-dense foods
                - Focus on healthy fats (avocados, nuts, olive oil)
                - Include protein-rich foods in every meal
                - Consider smaller, more frequent meals
                
                **Exercise Recommendations:**
                - Strength training 3-4 times per week
                - Limit excessive cardio
                - Focus on compound movements (squats, deadlifts, bench press)
                """)
            elif category == "Normal weight":
                st.success("""
                **Nutrition Recommendations:**
                - Maintain balanced macronutrients
                - Focus on whole foods and variety
                - Stay hydrated throughout the day
                - Monitor portion sizes to maintain weight
                
                **Exercise Recommendations:**
                - Mix cardio and strength training
                - Aim for 150 minutes of moderate exercise per week
                - Include flexibility and balance exercises
                - Try new activities to stay motivated
                """)
            elif category == "Overweight":
                st.warning("""
                **Nutrition Recommendations:**
                - Create a moderate calorie deficit (300-500 kcal/day)
                - Increase protein intake to preserve muscle mass
                - Focus on high-fiber foods for satiety
                - Limit processed foods and added sugars
                
                **Exercise Recommendations:**
                - Start with low-impact cardio (walking, swimming)
                - Gradually add strength training 2-3 times per week
                - Aim for 30 minutes of activity most days
                - Increase daily non-exercise activity (walking, stairs)
                """)
            else:  # Obese
                st.error("""
                **Nutrition Recommendations:**
                - Consult a nutritionist for personalized guidance
                - Focus on sustainable, long-term changes
                - Prioritize whole, minimally processed foods
                - Consider portion control strategies
                
                **Exercise Recommendations:**
                - Start with low-impact activities (water aerobics, cycling)
                - Gradually increase duration and intensity
                - Focus on consistency rather than intensity
                - Consider working with a physical therapist
                """)
        
        # Activity level recommendations
        st.write("### Based on Your Activity Level")
        activity = st.session_state.user_profile['activity_level']
        
        if activity == "Sedentary":
            st.info("""
            **To improve your health:**
            - Start with 10-15 minutes of activity daily
            - Take short walking breaks every hour
            - Consider standing desk options
            - Gradually build up to 150 minutes per week
            """)
        elif activity == "Lightly Active":
            st.success("""
            **To maintain your activity level:**
            - Aim for 150 minutes of moderate activity weekly
            - Include strength training twice per week
            - Try to reduce prolonged sitting time
            - Explore new activities to keep it interesting
            """)
        elif activity == "Moderately Active":
            st.info("""
            **To optimize your fitness:**
            - Include both cardio and strength training
            - Add high-intensity intervals 1-2 times per week
            - Focus on recovery and rest days
            - Monitor your progress and adjust as needed
            """)
        else:  # Very Active or Extra Active
            st.warning("""
            **To prevent overtraining:**
            - Ensure adequate rest and recovery time
            - Pay attention to nutrition and hydration
            - Consider periodization in your training
            - Listen to your body and adjust as needed
            - Get regular health check-ups
            """)

# ========================= PROFILE PAGE =========================
elif page == "👤 My Profile":
    st.title("👤 My Profile")
    
    # Account information section
    st.subheader("Account Information")
    st.markdown(f"**Name:** {st.session_state.user_profile.get('name', 'Not set')}")
    st.markdown(f"**Email:** {st.session_state.user_email}")
    st.markdown(f"**Member Since:** {datetime.now().strftime('%B %d, %Y')}")
    
    st.markdown("---")
    
    # Profile information section
    st.subheader("Personal Profile")
    
    # Calculate BMI
    bmi = calculate_bmi(
        st.session_state.user_profile['weight_kg'],
        st.session_state.user_profile['height_cm']
    )
    bmi_category, bmi_emoji = get_bmi_category(bmi) if bmi else ("N/A", "")
    
    # Calculate BMR and TDEE
    bmr = calculate_bmr(
        st.session_state.user_profile['weight_kg'],
        st.session_state.user_profile['height_cm'],
        st.session_state.user_profile['age'],
        st.session_state.user_profile['gender']
    )
    tdee = calculate_tdee(bmr, st.session_state.user_profile['activity_level'])
    
    # Display key metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Weight", f"{st.session_state.user_profile['weight_kg']} kg")
    with col2:
        st.metric("Height", f"{st.session_state.user_profile['height_cm']} cm")
    with col3:
        st.metric("BMI", f"{bmi:.1f} {bmi_emoji}", bmi_category)
    with col4:
        st.metric("Daily Energy Expenditure", f"{tdee:.0f} kcal")
    
    st.markdown("---")
    
    # Edit profile form
    st.subheader("Update Profile")
    
    with st.form("profile_form"):
        # Add name field at the top
        new_name = st.text_input(
            "Name", 
            value=st.session_state.user_profile.get('name', '')
        )
        
        col1, col2 = st.columns(2)
        
        with col1:
            new_weight = st.number_input(
                "Weight (kg)", 
                min_value=30.0, 
                max_value=300.0, 
                value=float(st.session_state.user_profile['weight_kg']), 
                step=0.5
            )
            new_height = st.number_input(
                "Height (cm)", 
                min_value=100.0, 
                max_value=250.0, 
                value=float(st.session_state.user_profile['height_cm']), 
                step=1.0
            )
            new_age = st.number_input(
                "Age", 
                min_value=10, 
                max_value=100, 
                value=st.session_state.user_profile['age']
            )
        
        with col2:
            new_gender = st.selectbox(
                "Gender", 
                ["Male", "Female"],
                index=0 if st.session_state.user_profile['gender'] == "Male" else 1
            )
            new_activity = st.selectbox(
                "Activity Level", 
                ['Sedentary', 'Lightly Active', 'Moderately Active', 'Very Active', 'Extra Active'],
                index=['Sedentary', 'Lightly Active', 'Moderately Active', 'Very Active', 'Extra Active']
                    .index(st.session_state.user_profile['activity_level'])
            )
            new_goal = st.selectbox(
                "Fitness Goal",
                ['Lose Weight', 'Maintain Weight', 'Gain Weight'],
                index=['Lose Weight', 'Maintain Weight', 'Gain Weight']
                    .index(st.session_state.user_profile['goal'])
            )
        
        submitted = st.form_submit_button("Update Profile")
    
    if submitted:
        # Update name in profile
        st.session_state.user_profile['name'] = new_name
        
        # Update other profile fields
        st.session_state.user_profile.update({
            'weight_kg': new_weight,
            'height_cm': new_height,
            'age': new_age,
            'gender': new_gender,
            'activity_level': new_activity,
            'goal': new_goal
        })
        
        # Recalculate goals based on new profile
        bmr = calculate_bmr(new_weight, new_height, new_age, new_gender)
        tdee = calculate_tdee(bmr, new_activity)
        
        if new_goal == 'Lose Weight':
            target_calories = tdee - 500
        elif new_goal == 'Gain Weight':
            target_calories = tdee + 500
        else:
            target_calories = tdee
        
        protein_g = (target_calories * 0.30) / 4
        carbs_g = (target_calories * 0.40) / 4
        fat_g = (target_calories * 0.30) / 9
        
        st.session_state.daily_goals.update({
            'calories': round(target_calories),
            'protein': round(protein_g),
            'carbs': round(carbs_g),
            'fat': round(fat_g)
        })
        
        st.success("Profile updated successfully! Your daily goals have been recalculated.")
        st.rerun()
    
    # Password change section
    st.markdown("---")
    st.subheader("Change Password")
    
    with st.form("password_change_form"):
        st.write("### Update Your Password")
        
        col1, col2 = st.columns(2)
        with col1:
            new_password = st.text_input("New Password", type="password", 
                                        help="Use 12+ characters with uppercase, lowercase, numbers, and symbols")
            st.caption("Password requirements:")
            st.caption("- At least 12 characters")
            st.caption("- Uppercase and lowercase letters")
            st.caption("- At least one number")
            st.caption("- At least one special character")
        
        with col2:
            confirm_password = st.text_input("Confirm New Password", type="password")
            st.caption("Password strength:")
            if new_password:
                is_strong, msg = is_strong_password(new_password)
                if is_strong:
                    st.success("✅ Password meets strength requirements")
                else:
                    st.error(f"❌ {msg}")
            
        submitted_pw = st.form_submit_button("Change Password")
        
        if submitted_pw:
            if new_password != confirm_password:
                st.error("Passwords do not match!")
            else:
                success, message = firebase_change_password(new_password)
                if success:
                    st.success(message)
                    st.rerun()
                else:
                    st.error(message)
    
    # Account management section
    st.markdown("---")
    st.subheader("Account Management")
    
    with st.expander("Danger Zone"):
        st.warning("These actions are irreversible. Proceed with caution.")
        
        # Use a session state to manage the confirmation step
        if 'confirm_delete' not in st.session_state:
            st.session_state.confirm_delete = False
            
        if not st.session_state.confirm_delete:
            if st.button("Delete All My Data", type="secondary"):
                st.session_state.confirm_delete = True
                st.rerun()
        else:
            st.error("⚠️ This will permanently delete ALL your data and cannot be undone. Are you sure?")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Yes, Delete Everything", type="primary"):
                    if db:
                        try:
                            user_ref = db.collection(USER_DATA_COLLECTION).document(st.session_state.user_id)
                            
                            # Delete all subcollections
                            for collection_name in [
                                FOOD_DIARY_SUBCOLLECTION,
                                EXERCISE_LOG_SUBCOLLECTION,
                                WEIGHT_LOG_SUBCOLLECTION,
                                WATER_LOG_SUBCOLLECTION
                            ]:
                                # Delete all documents in the subcollection
                                collection_ref = user_ref.collection(collection_name)
                                docs = collection_ref.stream()
                                for doc in docs:
                                    doc.reference.delete()
                            
                            # Delete the main document
                            user_ref.delete()
                            
                            # Reset session state
                            st.session_state.authenticated = False
                            st.session_state.user_email = None
                            st.session_state.user_id = None
                            st.session_state.password_breach_warning = False
                            st.session_state.confirm_delete = False
                            
                            st.success("All your data has been permanently deleted.")
                            time.sleep(2)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to delete data: {e}")
                    else:
                        st.error("Database connection not available. Data could not be deleted.")
            with col2:
                if st.button("Cancel", type="secondary"):
                    st.session_state.confirm_delete = False
                    st.rerun()

# ... existing code ...

# ========================= USER GUIDE PAGE =========================
elif page == "📖 User Guide":
    st.title("📖 FitVerse User Guide")
    st.markdown("Welcome to FitVerse! This guide will help you get started with our complete fitness tracking platform.")
    
    # Create tabs for different sections
    tab1, tab2, tab3, tab4 = st.tabs(["Getting Started", "Logging Basics", "Goal Setting", "Advanced Features"])
    
    with tab1:
        st.subheader(">> Getting Started")
        st.markdown("""
        ### Step 1: Set Up Your Profile
        1. Go to **👤 My Profile** page
        2. Enter your personal details (name, age, gender)
        3. Add your current weight and height
        4. Select your activity level
        5. Choose your fitness goal
        6. Click **Update Profile**
        
        ### Step 2: Set Your Goals
        1. Go to **BMI & Goals** page
        2. Select the **Goal Setting** tab
        3. Review your automatically calculated goals
        4. Adjust as needed based on your preferences
        5. Click **Save Custom Goals**
        
        ### Step 3: Start Tracking
        - Log your first meal in **Food Log**
        - Record your first workout in **Exercise Log**
        - Track your weight in **Progress Tracking**
        """)
        
        # Replaced image with descriptive text
        st.info("📋 **Profile setup is your first step to success**")
        st.markdown("""
        Your profile information helps us calculate your personalized goals and recommendations. 
        Make sure to update it whenever your fitness situation changes!
        """)
    
    with tab2:
        st.subheader(">> Logging Basics")
        st.markdown("""
        ### Food Logging
        1. Go to **Food Log**
        2. Use the search tab to find foods from our database
        3. Select meal type and quantity
        4. Click **Add to diary**
        5. Use **Quick Add** for custom foods
        
        ### Exercise Logging
        1. Go to **Exercise Log**
        2. Select an activity from our library
        3. Enter duration and intensity
        4. Review estimated calories burned
        5. Click **Log Exercise**
        
        ### Water Tracking
        1. Go to **Progress Tracking**
        2. Select the **Water Intake** tab
        3. Enter glasses of water consumed
        4. Click **Log Water**
        """)
        
        col1, col2 = st.columns(2)
        with col1:
            st.info("**Food Logging**")
            st.markdown("""
            - Search our extensive food database
            - See nutrition information instantly
            - Log meals in seconds
            """)
        
        with col2:
            st.info("**Exercise Logging**")
            st.markdown("""
            - Choose from 20+ activities
            - Automatic calorie calculation
            - Track intensity levels
            """)
    
    with tab3:
        st.subheader(">> Setting Effective Goals")
        st.markdown("""
        ### Understanding Your Goals
        - **Calories:** Your daily energy target
        - **Macros:** Protein, carbs and fat targets
        - **Water:** Daily hydration goal
        
        ### How We Calculate Goals
        Based on your profile, we calculate:
        - **BMR:** Basal Metabolic Rate (calories at rest)
        - **TDEE:** Total Daily Energy Expenditure
        - **Goal Adjustment:** 
          - Weight Loss: TDEE - 500 calories
          - Maintenance: TDEE
          - Weight Gain: TDEE + 500 calories
        
        ### Tips for Success
        1. Start with realistic goals
        2. Focus on consistency over perfection
        3. Adjust goals every 2-4 weeks
        4. Celebrate small victories
        5. Use the dashboard to track progress
        """)
        
        st.info("**Your goals dashboard helps you stay on track**")
        st.markdown("""
        | Goal Type | Calculation Formula |
        |-----------|---------------------|
        | Calories | Based on your TDEE and fitness goal |
        | Protein  | 30% of total calories ÷ 4 calories/gram |
        | Carbs    | 40% of total calories ÷ 4 calories/gram |
        | Fat      | 30% of total calories ÷ 9 calories/gram |
        """)
    
    with tab4:
        st.subheader(">> Advanced Features")
        st.markdown("""
        ### Progress Tracking
        - **Weight Trends:** Visualize your weight journey
        - **Calorie Analysis:** See your net calorie balance
        - **Macro Breakdown:** Analyze your nutrition patterns
        - **Water History:** Track your hydration consistency
        
        ### BMI Calculator
        - Understand your body composition
        - Get personalized recommendations
        - See your ideal weight range
        
        ### Data Security
        - Military-grade encryption
        - Breached password protection
        - Automatic cloud backups
        - GDPR-compliant data handling
        
        ### Pro Tips
        - Use the **Quick Add** feature for custom recipes
        - Log your weight daily for best results
        - Check the dashboard every morning
        - Save to cloud regularly
        - Set reminders for water intake
        """)
        
        st.info("💡 **Expert Tip:** Log your food before eating to stay accountable to your goals!")
    
    # Final section with contact info
    st.markdown("---")
    st.subheader("Need More Help?")
    st.markdown("""
    - 📧 Email us at huzaifanawaid.developer@gmail.com
    - 💬 Chat with us in the app (coming soon)
    """)
    
    st.markdown("""
    <style>
        .guide-section {
            background-color: #f9f9f9;
            border-radius: 10px;
            padding: 20px;
            margin: 15px 0;
            border-left: 4px solid #4e73df;
        }
        .guide-tip {
            background-color: #e8f4fd;
            border-radius: 10px;
            padding: 15px;
            margin: 15px 0;
            border-left: 4px solid #3498db;
        }
    </style>
    """, unsafe_allow_html=True)