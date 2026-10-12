# Hospital Appointment Workflow

## Description

Handle hospital and appointment workflows by combining symptom lookup, emergency knowledge, appointment registration, appointment query, modification, cancellation, and optional agenda follow-up.

## Use Cases

- Search symptoms and emergency guidance before choosing a doctor
- Register a patient appointment with date and doctor
- Query appointment status before changing or canceling it
- Modify appointment date or doctor
- Add an agenda item for the confirmed appointment

## Workflow

### Step 1: Inspect symptom or emergency knowledge
- **Tool**: `SymptomSearch` or `EmergencyKnowledge` × 1-n times
- **Examples**:
  - `SymptomSearch({"symptom": "headache"})`
  - `EmergencyKnowledge({"symptom": "chest pain"})`
- **Purpose**: Ground the medical scenario in API evidence before scheduling.

### Step 2: Register appointment
- **Tool**: `AppointmentRegistration`
- **Example**: `AppointmentRegistration({"patient_name": "Alice", "date": "2023-04-06", "doctor_name": "Dr. Smith"})`
- **Purpose**: Create a concrete appointment record.

### Step 3: Query appointment
- **Tool**: `QueryRegistration` × 1-n times
- **Example**: `QueryRegistration({"patient_name": "Alice", "date": "2023-04-06"})`
- **Purpose**: Verify the appointment and retrieve the appointment identifier if available.

### Step 4: Modify appointment if needed
- **Tool**: `ModifyRegistration`
- **Example**: `ModifyRegistration({"appointment_id": "appointment_id_from_query", "new_appointment_date": "2023-04-07", "new_appointment_doctor": "Dr. Brown"})`
- **Purpose**: Exercise rescheduling or doctor-change workflows.

### Step 5: Add calendar follow-up
- **Tool**: `GetUserToken` then `AddAgenda`
- **Examples**:
  - `GetUserToken({"username": "John", "password": "123456"})`
  - `AddAgenda({"token": "returned_token", "content": "hospital appointment with Dr. Brown", "time": "2023-04-07 09:00:00", "location": "City Hospital"})`
- **Purpose**: Connect appointment state with personal planning state.

### Step 6: Cancel obsolete appointment when required
- **Tool**: `CancelRegistration`
- **Example**: `CancelRegistration({"appointment_id": "appointment_id_from_query"})`
- **Purpose**: Remove appointment state when the scenario requires cancellation.

### Step 7: Verify final appointment state
- **Tool**: `QueryRegistration` × 1-n times
- **Example**: `QueryRegistration({"patient_name": "Alice", "date": "2023-04-07"})`
- **Purpose**: Confirm registration, modification, or cancellation.

## Tools Involved

`SymptomSearch`, `EmergencyKnowledge`, `AppointmentRegistration`, `QueryRegistration`, `ModifyRegistration`, `CancelRegistration`, `GetUserToken`, `AddAgenda`

## Tips

- Use `QueryRegistration` after creation before calling `ModifyRegistration` or `CancelRegistration`.
- `ModifyRegistration` only requires `appointment_id`; new date and doctor are optional but at least one should be meaningful.
- Add agenda only after the appointment details are settled.
