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

# Page configuration
st.set_page_config(
    page_title="FitTrack Pro - Complete Fitness Tracker",
    page_icon="💪",
    layout="wide",
    initial_sidebar_state="expanded"
)

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
</style>
""", unsafe_allow_html=True)

# ========================= UTILITIES =========================

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

# ========================= SESSION STATE =========================

# Initialize session state
if 'food_diary' not in st.session_state:
    st.session_state.food_diary = pd.DataFrame(
        columns=['date', 'meal', 'food_name', 'brand', 'calories', 'protein', 
                'carbs', 'fat', 'fiber', 'quantity', 'serving_size']
    )

if 'exercise_log' not in st.session_state:
    st.session_state.exercise_log = pd.DataFrame(
        columns=['date', 'activity', 'duration_min', 'calories_burned', 'intensity']
    )

if 'weight_log' not in st.session_state:
    st.session_state.weight_log = pd.DataFrame(
        columns=['date', 'weight_kg']
    )

if 'water_log' not in st.session_state:
    st.session_state.water_log = pd.DataFrame(
        columns=['date', 'glasses']
    )

if 'user_profile' not in st.session_state:
    st.session_state.user_profile = {
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

st.sidebar.title("🏋️ FitTrack Pro")
st.sidebar.markdown("---")

# Navigation
page = st.sidebar.selectbox(
    "Navigate to",
    ["📊 Dashboard", "🍽️ Food Log", "💪 Exercise Log", 
     "📈 Progress Tracking", "⚖️ BMI & Goals"]
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
water_glasses = today_water['glasses'].sum() if not today_water.empty else 0

st.sidebar.metric("Net Calories Today", f"{net_calories:.0f}")
st.sidebar.metric("Water (glasses)", f"{water_glasses:.0f}")

# ========================= PAGES =========================

if page == "📊 Dashboard":
    st.title("📊 Fitness Dashboard")
    st.markdown(f"### Welcome back! Today is {today.strftime('%B %d, %Y')}")
    
    # Top metrics row
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        progress = (calories_consumed / st.session_state.daily_goals['calories']) * 100
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
        st.subheader("🥗 Macronutrients Breakdown")
        if not today_food.empty:
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
        st.subheader("🍽️ Recent Meals")
        if not today_food.empty:
            recent_meals = today_food[['meal', 'food_name', 'calories']].tail(5)
            st.dataframe(recent_meals, hide_index=True)
        else:
            st.info("No meals logged today")
    
    with col2:
        st.subheader("💪 Recent Exercises")
        if not today_exercise.empty:
            recent_ex = today_exercise[['activity', 'duration_min', 'calories_burned']].tail(5)
            st.dataframe(recent_ex, hide_index=True)
        else:
            st.info("No exercises logged today")

elif page == "🍽️ Food Log":
    st.title("🍽️ Food Log")
    
    tab1, tab2, tab3 = st.tabs(["Search & Add Food", "Today's Log", "Quick Add"])
    
    with tab1:
        st.subheader("Search Food Database")
        
        col1, col2 = st.columns([3, 1])
        with col1:
            search_query = st.text_input("Search for food (e.g., 'chicken breast', 'apple')")
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
                                meal_type = st.selectbox(f"Meal_{idx}", 
                                    ["Breakfast", "Lunch", "Dinner", "Snack"],
                                    key=f"meal_{idx}")
                                quantity = st.number_input(f"Quantity_{idx}", 
                                    min_value=0.1, value=1.0, step=0.1, key=f"qty_{idx}")
                            
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
            with col1:
                st.metric("Calories", f"{today_food['calories'].sum():.0f}")
            with col2:
                st.metric("Protein", f"{today_food['protein'].sum():.1f}g")
            with col3:
                st.metric("Carbs", f"{today_food['carbs'].sum():.1f}g")
            with col4:
                st.metric("Fat", f"{today_food['fat'].sum():.1f}g")
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

