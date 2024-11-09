from flask import Flask, render_template, request, jsonify
import requests
from datetime import datetime
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
from unidecode import unidecode
import re

app = Flask(__name__)

API_KEY = "716271569df24ee8a11100903242910"
BASE_URL = "http://api.weatherapi.com/v1/current.json"


def normalize_city_name(city):
    city_aliases = {
    "hanoi": "ha noi",
    "hochiminh": "ho chi minh",
    "danang": "da nang",
    # Bổ sung các tên thành phố khác nếu cần
}
    # Loại bỏ dấu tiếng Việt, chuyển sang chữ thường và loại bỏ khoảng trắng thừa
    city = unidecode(city).lower().strip()
    # Thay thế tên thành phố bằng dạng chuẩn nếu có trong danh sách alias
    city = city_aliases.get(city, city)
    return city

def get_weather_data(city):
    response = requests.get(f"{BASE_URL}?key={API_KEY}&q={city}&aqi=no")
    if response.status_code == 200:
        return response.json()
    return None


@app.route('/')
def index():
    # Không trả về thông tin thời tiết ban đầu để giao diện chỉ hiển thị dòng chữ "Trang dự báo thời tiết"
    return render_template('index.html', current_weather=None)

@app.route('/weather', methods=['POST'])
def get_weather():
    city = request.form.get('city')
    city = normalize_city_name(city)
    weather_data = get_weather_data(city)
    if weather_data:
        current_date = datetime.strptime(weather_data['location']['localtime'], "%Y-%m-%d %H:%M").date()
        current_weather = {
            'location': weather_data['location']['name'],
            'temp_c': weather_data['current']['temp_c'],
            'condition': weather_data['current']['condition']['text'],
            'icon': weather_data['current']['condition']['icon'],
            'lat': weather_data['location']['lat'],
            'lon': weather_data['location']['lon'],
            'date': current_date.strftime("%d/%m/%Y")
        }
        return jsonify(current_weather)
    else:
        return jsonify({'error': 'City not found!'}), 404


def predict_weather(data, start_date=None):
    if start_date is None:
        start_date = datetime.now().strftime('%Y-%m-%d')
    
    features = ['tempmax', 'tempmin', 'humidity']
    target_tempmax = 'tempmax'
    target_tempmin = 'tempmin'
    target_precip_type = 'preciptype'

    # Kiểm tra xem các cột cần thiết có tồn tại trong dữ liệu hay không
    if not all(col in data.columns for col in features + [target_tempmax, target_tempmin, target_precip_type, 'datetime']):
        print("Data is insufficient for prediction.")
        return []

    # Xử lý giá trị NaN cho cột precip_type
    data[target_precip_type] = data[target_precip_type].fillna("none")  # Thay thế NaN bằng "none"

    # Chuyển đổi cột 'datetime' thành kiểu ngày tháng
    data['datetime'] = pd.to_datetime(data['datetime'], errors='coerce')
    data = data.dropna(subset=['datetime'])  # Bỏ các hàng không có ngày tháng hợp lệ

    # Huấn luyện mô hình dự đoán nhiệt độ
    model_tempmax = RandomForestRegressor(n_estimators=100, random_state=42)
    model_tempmin = RandomForestRegressor(n_estimators=100, random_state=42)

    X = data[features]
    y_tempmax = data[target_tempmax]
    y_tempmin = data[target_tempmin]

    model_tempmax.fit(X, y_tempmax)
    model_tempmin.fit(X, y_tempmin)

    # Huấn luyện mô hình dự đoán loại mưa
    model_precip = RandomForestClassifier(n_estimators=100, random_state=42)
    model_precip.fit(X, data[target_precip_type])

    predictions = []
    last_row = data.iloc[-1]
    start_date = pd.to_datetime(start_date)

    # Dự đoán thời tiết cho 7 ngày tiếp theo
    for i in range(1, 8):
        next_date = start_date + pd.Timedelta(days=i)
        new_data = pd.DataFrame({
            'tempmax': [last_row['tempmax'] + np.random.uniform(-2, 2)],
            'tempmin': [last_row['tempmin'] + np.random.uniform(-2, 2)],
            'humidity': [last_row['humidity'] + np.random.uniform(-10, 10)]
        })

        predicted_tempmax = model_tempmax.predict(new_data)[0]
        predicted_tempmin = model_tempmin.predict(new_data)[0]
        predicted_temp = (predicted_tempmax + predicted_tempmin) / 2

        # Dự đoán precip_type dựa trên mô hình
        predicted_precip_type = model_precip.predict(new_data)[0]

        predictions.append({
            'date': next_date.strftime('%Y-%m-%d'),
            'tempmax': predicted_tempmax,
            'tempmin': predicted_tempmin,
            'temp': predicted_temp,
            'precip_type': predicted_precip_type
        })

    return predictions



@app.route('/forecast', methods=['POST'])
def forecast():
    data = request.json  # Hoặc request.form nếu bạn gửi dữ liệu dưới dạng form
    city = data.get('city')  # Hoặc data['city'] nếu bạn chắc chắn nó sẽ có giá trị
    city = normalize_city_name(city)
    if not city:
        return jsonify({"error": "City is required!"}), 400

    file_path = f"{city.replace(' ', '_')}.csv"

    try:
        data = pd.read_csv(file_path)
        predictions = predict_weather(data)
        return jsonify(predictions)
    except FileNotFoundError:
        return jsonify({'error': 'Data file not found for this city.'}), 404


def get_coordinates(city):
    response = requests.get(f"{BASE_URL}?key={API_KEY}&q={city}&aqi=no")
    if response.status_code == 200:
        data = response.json()
        return data['location']['lon'], data['location']['lat']
    return None, None

if __name__ == '__main__':
    app.run(debug=True)