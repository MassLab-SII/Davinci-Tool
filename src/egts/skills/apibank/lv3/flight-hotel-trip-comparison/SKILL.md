# Flight Hotel Trip Comparison

## Description

Compare travel options by checking flights, hotel availability, location evidence, and simple arithmetic summaries. This skill focuses on itinerary comparison rather than general destination assistance.

## Use Cases

- Compare whether a destination has both flight and hotel availability
- Check several travel dates for possible options
- Summarize lodging or flight availability across multiple candidate dates
- Ground a trip comparison in city coordinates and returned API evidence

## Workflow

### Step 1: Search for trip planning tools
- **Tool**: `Lv3ToolSearcher`
- **Example**: `Lv3ToolSearcher({"keywords": "flight hotel trip availability"})`
- **Purpose**: Find the relevant flight and hotel APIs before calling them.

### Step 2: Ground the destination
- **Tool**: `Geocoding`
- **Example**: `Geocoding({"address": "San Francisco"})`
- **Purpose**: Confirm the destination and provide location evidence for the trip.

### Step 3: Search flights
- **Tool**: `FlightSearch` × 1-n times
- **Examples**:
  - `FlightSearch({"source": "New York", "destination": "San Francisco", "travel_dates": "2022-01-01"})`
  - `FlightSearch({"source": "Los Angeles", "destination": "San Francisco", "travel_dates": "2022-01-02"})`
- **Purpose**: Retrieve flight candidates. Repeat for different seeded source/date combinations when comparing routes.

### Step 4: Search hotel availability
- **Tool**: `HotelAvailability` × 1-n times
- **Examples**:
  - `HotelAvailability({"destination": "San Francisco", "check_in_date": "2022-01-01", "check_out_date": "2022-01-02"})`
  - `HotelAvailability({"destination": "San Francisco", "check_in_date": "2022-01-02", "check_out_date": "2022-01-03"})`
- **Purpose**: Retrieve hotels that match the travel dates.

### Step 5: Calculate comparison totals
- **Tool**: `Lv3Calculator`
- **Example**: `Lv3Calculator({"formula": "1 + 1"})`
- **Purpose**: Count available options or compare simple numeric summaries.

### Step 6: Re-check one selected option
- **Tool**: `FlightSearch` or `HotelAvailability`
- **Example**: `HotelAvailability({"destination": "San Francisco", "check_in_date": "2022-01-01", "check_out_date": "2022-01-02"})`
- **Purpose**: Verify the chosen trip option with a repeated lookup.

## Tools Involved

`Lv3ToolSearcher`, `FlightSearch`, `HotelAvailability`, `Geocoding`, `Lv3Calculator`

## Tips

- Use date strings in `%Y-%m-%d` format.
- Seeded flights include routes such as `New York` to `San Francisco`.
- Seeded hotels are mostly in `San Francisco`; use that destination for higher success rates.
- Repeated lookups are useful evidence when choosing between multiple itinerary options.

