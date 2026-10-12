# Travel Weather Restaurant Planning

## Description

Plan travel and local activity workflows by grounding a destination with coordinates, checking weather, selecting clothing, finding nearby restaurants, and optionally checking flights and hotels. This skill covers API-Bank Level-3 life-service scenarios where the agent must compose multiple read-only APIs into a useful trip plan.

## Use Cases

- Convert a city or place name into coordinates and check the local weather
- Recommend clothing for a trip based on weather conditions
- Find restaurants near a destination before travel
- Combine location, flight, hotel, and weather evidence into a grounded itinerary

## Workflow

### Step 1: Discover relevant travel APIs
- **Tool**: `Lv3ToolSearcher`
- **Example**: `Lv3ToolSearcher({"keywords": "travel weather restaurants hotel flight"})`
- **Purpose**: Identify which Level-3 APIs are useful for the active travel or destination workflow.

### Step 2: Convert destination to coordinates
- **Tool**: `Geocoding`
- **Example**: `Geocoding({"address": "San Francisco"})`
- **Purpose**: Obtain latitude and longitude for downstream weather and restaurant lookup. Use known seeded places such as `New York City`, `San Francisco`, `London`, `Paris`, or `Tokyo`.

### Step 3: Check weather
- **Tool**: `GetWeatherForCoordinates`
- **Example**: `GetWeatherForCoordinates({"latitude": 37.7749, "longitude": 122.4194})`
- **Purpose**: Retrieve weather evidence for the destination.

### Step 4: Recommend clothing
- **Tool**: `ClothingRecommendation`
- **Example**: `ClothingRecommendation({"temperature": 20, "humidity": 0.8, "weather_conditions": "Cloudy"})`
- **Purpose**: Convert weather data into practical clothing advice.

### Step 5: Find nearby restaurants
- **Tool**: `NearbyRestaurants`
- **Example**: `NearbyRestaurants({"latitude": 37.7749, "longitude": 122.4194, "distance": 1000})`
- **Purpose**: Add local food options to the destination plan.

### Step 6: Check transport and lodging
- **Tool**: `FlightSearch` or `HotelAvailability` × 1-n times
- **Examples**:
  - `FlightSearch({"source": "New York", "destination": "San Francisco", "travel_dates": "2022-01-01"})`
  - `HotelAvailability({"destination": "San Francisco", "check_in_date": "2022-01-01", "check_out_date": "2022-01-02"})`
- **Purpose**: Retrieve available flight or hotel options for the trip. Repeat with nearby dates or cities when comparing options.

### Step 7: Calculate a simple summary if needed
- **Tool**: `Lv3Calculator`
- **Example**: `Lv3Calculator({"formula": "3 + 2"})`
- **Purpose**: Compute counts, day spans, or simple trip totals from retrieved evidence.

## Tools Involved

`Lv3ToolSearcher`, `Geocoding`, `GetWeatherForCoordinates`, `ClothingRecommendation`, `NearbyRestaurants`, `FlightSearch`, `HotelAvailability`, `Lv3Calculator`

## Tips

- Use exact seeded place names and date formats to avoid empty lookups.
- Weather coordinates must exactly match coordinates returned by `Geocoding`.
- Use `NearbyRestaurants` after geocoding; do not invent coordinates.
- Use `FlightSearch` and `HotelAvailability` multiple times when the task asks for comparison.

