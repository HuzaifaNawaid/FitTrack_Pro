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

elif page == "💪 Exercise Log":
    st.title("💪 Exercise Log")
    
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
    st.title("📈 Progress Tracking")
    
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
            # Aggregate calories by date
            daily_calories = st.session_state.food_diary.groupby('date')['calories'].sum().reset_index()
            
            if not st.session_state.exercise_log.empty:
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
    st.title("⚖️ BMI Calculator & Goal Setting")
    
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
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("### Personal Information")
            age = st.number_input("Age", min_value=10, max_value=100, 
                                value=st.session_state.user_profile['age'])
            gender = st.selectbox("Gender", ["Male", "Female"],
                                index=0 if st.session_state.user_profile['gender'] == "Male" else 1)
            activity = st.selectbox("Activity Level", 
                                  ['Sedentary', 'Lightly Active', 'Moderately Active', 'Very Active', 'Extra Active'],
                                  index=['Sedentary', 'Lightly Active', 'Moderately Active', 'Very Active', 'Extra Active']
                                  .index(st.session_state.user_profile['activity_level']))
            goal = st.selectbox("Fitness Goal",
                              ['Lose Weight', 'Maintain Weight', 'Gain Weight'],
                              index=['Lose Weight', 'Maintain Weight', 'Gain Weight']
                              .index(st.session_state.user_profile['goal']))
            
            if st.button("Update Profile & Calculate Goals"):
                st.session_state.user_profile.update({
                    'age': age,
                    'gender': gender,
                    'activity_level': activity,
                    'goal': goal
                })
                
                # Calculate BMR and TDEE
                bmr = calculate_bmr(st.session_state.user_profile['weight_kg'],
                                  st.session_state.user_profile['height_cm'],
                                  age, gender)
                tdee = calculate_tdee(bmr, activity)
                
                # Adjust for goal
                if goal == 'Lose Weight':
                    target_calories = tdee - 500  # 500 calorie deficit
                elif goal == 'Gain Weight':
                    target_calories = tdee + 500  # 500 calorie surplus
                else:
                    target_calories = tdee
                
                # Calculate macro split (40% carbs, 30% protein, 30% fat for balanced diet)
                protein_g = (target_calories * 0.30) / 4
                carbs_g = (target_calories * 0.40) / 4
                fat_g = (target_calories * 0.30) / 9
                
                st.session_state.daily_goals.update({
                    'calories': round(target_calories),
                    'protein': round(protein_g),
                    'carbs': round(carbs_g),
                    'fat': round(fat_g)
                })
                
                st.success("Goals updated successfully!")
                st.rerun()
        
        with col2:
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
        
        # Calculate BMR and TDEE for recommendations
        bmr = calculate_bmr(st.session_state.user_profile['weight_kg'],
                          st.session_state.user_profile['height_cm'],
                          st.session_state.user_profile['age'],
                          st.session_state.user_profile['gender'])
        tdee = calculate_tdee(bmr, st.session_state.user_profile['activity_level'])
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("### 📊 Your Metabolic Profile")
            st.metric("Basal Metabolic Rate (BMR)", f"{bmr:.0f} kcal/day")
            st.metric("Total Daily Energy Expenditure (TDEE)", f"{tdee:.0f} kcal/day")
            
            st.write("### 🎯 Goal-Based Recommendations")
            goal = st.session_state.user_profile['goal']
            
            if goal == 'Lose Weight':
                st.info("""
                **Weight Loss Strategy:**
                - Target: 500-750 calorie deficit daily
                - Expected loss: 0.5-0.75 kg per week
                - Focus on high-protein, high-fiber foods
                - Include strength training to preserve muscle
                """)
            elif goal == 'Gain Weight':
                st.info("""
                **Weight Gain Strategy:**
                - Target: 300-500 calorie surplus daily
                - Expected gain: 0.25-0.5 kg per week
                - Focus on nutrient-dense foods
                - Progressive overload in strength training
                """)
            else:
                st.info("""
                **Weight Maintenance Strategy:**
                - Maintain current calorie intake
                - Balance macronutrients
                - Focus on food quality
                - Regular exercise for health benefits
                """)
        
        with col2:
            st.write("### 🍽️ Meal Timing Suggestions")
            meal_distribution = {
                'Breakfast': 25,
                'Morning Snack': 10,
                'Lunch': 30,
                'Afternoon Snack': 10,
                'Dinner': 25
            }
            
            total_cal = st.session_state.daily_goals['calories']
            for meal, percentage in meal_distribution.items():
                cal_per_meal = (percentage / 100) * total_cal
                st.write(f"**{meal}:** {cal_per_meal:.0f} kcal ({percentage}%)")
            
            st.write("### 💧 Hydration Guidelines")
            water_needs = st.session_state.user_profile['weight_kg'] * 0.033
            st.info(f"""
            **Recommended Water Intake:**
            - Minimum: {water_needs:.1f} liters/day
            - Active days: {water_needs * 1.5:.1f} liters/day
            - Hot weather: Add 500ml extra
            - During exercise: 200ml every 20 minutes
            """)

