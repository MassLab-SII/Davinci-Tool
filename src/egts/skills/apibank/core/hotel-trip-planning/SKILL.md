# Hotel Trip Planning

## Description

Plan travel-like workflows with hotel booking, calendar agenda, meeting coordination, and alarm setup. This skill is based on API-Bank hotel booking and Level-3 hotel scenes.

## Use Cases

- Book a hotel for a trip
- Add a travel agenda item
- Schedule a meeting around the hotel stay
- Set an alarm for check-in, checkout, or travel departure
- Verify booked or scheduled records

## Workflow

### Step 1: Book hotel
- **Tool**: `BookHotel`
- **Example**: `BookHotel({"hotel_name": "Grand Hotel", "check_in_time": "2023-04-10", "check_out_time": "2023-04-12", "room_count": 1, "adult_count": 2, "child_count": 0})`
- **Purpose**: Create the central travel booking record.

### Step 2: Retrieve token
- **Tool**: `GetUserToken`
- **Example**: `GetUserToken({"username": "John", "password": "123456"})`
- **Purpose**: Token-protected agenda, meeting, and alarm tools need authentication.

### Step 3: Add trip agenda
- **Tool**: `AddAgenda`
- **Example**: `AddAgenda({"token": "returned_token", "content": "hotel check-in at Grand Hotel", "time": "2023-04-10 15:00:00", "location": "Grand Hotel"})`
- **Purpose**: Reflect hotel booking in the user's calendar.

### Step 4: Schedule trip meeting if needed
- **Tool**: `AddMeeting`
- **Example**: `AddMeeting({"token": "returned_token", "meeting_topic": "trip planning call", "start_time": "2023-04-09 19:00:00", "end_time": "2023-04-09 19:30:00", "location": "online", "attendees": ["alice@example.com"]})`
- **Purpose**: Coordinate travel-related participants or tasks.

### Step 5: Query meeting or agenda evidence
- **Tool**: `QueryMeeting` or `QueryAgenda` × 1-n times
- **Example**: `QueryAgenda({"token": "returned_token", "content": "hotel check-in at Grand Hotel", "time": "2023-04-10 15:00:00", "location": "Grand Hotel"})`
- **Purpose**: Verify that trip planning state was stored.

### Step 6: Add alarm
- **Tool**: `AddAlarm`
- **Example**: `AddAlarm({"token": "returned_token", "time": "2023-04-10 13:30:00"})`
- **Purpose**: Add a timed alert for travel departure or check-in.

### Step 7: Calculate duration or cost when useful
- **Tool**: `Calculator`
- **Example**: `Calculator({"formula": "12 - 10"})`
- **Purpose**: Compute stay duration, room counts, or budget estimates from the booking.

## Tools Involved

`BookHotel`, `GetUserToken`, `AddAgenda`, `QueryAgenda`, `AddMeeting`, `QueryMeeting`, `AddAlarm`, `Calculator`

## Tips

- `room_count`, `adult_count`, and `child_count` must be numbers.
- Use date strings consistently across hotel, agenda, and alarm calls.
- Verify agenda or meeting state after creating travel plans.
