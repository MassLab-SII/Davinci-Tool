"""Fallback prompt fragments for trajectory synthesis.

This module centralizes text templates used by data_synthesis fallback logic,
so prompt-like content can be reviewed in one place under prompts/.
"""

from __future__ import annotations

SYNTHESIS_SYSTEM_PROMPT = (
    "You are a practical agent that plans briefly, observes outputs, and adapts each next tool action to complete the user's task."
)

# Ordered rules for mapping tool names to concise step intents.
# Each tuple is: (match_type, keywords, intent_text)
# - match_type: "contains" or "exact"
# Rules are evaluated in order, FIRST MATCH WINS.
# Ordering principle: most specific patterns first, then broader ones.

TOOL_INTENT_RULES = [
    # --- Filesystem: directory listing (specific → general) ---
    (
        "contains",
        ("list_directory_with_sizes",),
        "list the target directory with sizes to retrieve the requested information",
    ),
    (
        "contains",
        ("list_allowed_directories", "list_directory", "directory_tree"),
        "list the directory contents the user asked about to retrieve the needed information",
    ),
    # --- Environment / state inspection ---
    (
        "contains",
        ("get_environment_info", "get_command_history", "get_available_actions",
         "get_current_task", "get_instruction", "get_page_observation",
         "get_dom_elements", "get_observation", "get_call_trace"),
        "retrieve the current task details and environment state to understand what needs to be done",
    ),
    # --- ToolSandbox: device state inspection ---
    (
        "contains",
        ("get_wifi_status", "get_location_service_status",
         "get_low_battery_mode_status", "get_bluetooth_status",
         "get_cellular_status", "get_device_status",
         "get_screen_brightness", "get_volume_level"),
        "check the device setting the user asked about to determine its current state",
    ),
    # --- ToolSandbox: time inspection / computation ---
    (
        "contains",
        ("get_current_timestamp", "get_current_time",
         "timestamp_to_datetime_info", "datetime_info_to_timestamp",
         "timestamp_diff", "seconds_to_hours_minutes_seconds",
         "convert_timezone", "get_timezone"),
        "retrieve or compute the time information the user requested to complete the task",
    ),
    # --- ToolSandbox: unit conversion ---
    (
        "contains",
        ("unit_conversion", "convert_units", "convert_temperature",
         "convert_distance", "convert_weight"),
        "convert the measurement to the unit the user requested",
    ),
    # --- ToolSandbox: location ---
    (
        "contains",
        ("get_current_location", "get_location", "get_gps_coordinates",
         "get_navigation_route"),
        "retrieve the location data the user asked about",
    ),
    # --- API discovery (specific: before generic "search") ---
    (
        "contains",
        ("search_appworld_apis", "search_candidate_apis", "list_candidate_apis",
         "ToolSearcher", "search_appworld", "search_candidate"),
        "locate the exact API endpoint needed to fulfill the user's request",
    ),
    # --- API inspection ---
    (
        "contains",
        ("get_api_schema", "get_appworld_api_schema", "get_appworld_api"),
        "retrieve the API specification to construct a correct call",
    ),
    # --- API calling ---
    (
        "contains",
        ("call_api", "shift_timestamp"),
        "call the API with the correct parameters to fulfill the request",
    ),
    # --- Specific search patterns (before generic "search") ---
    (
        "contains",
        ("search_product",),
        "search for the specific item the user requested",
    ),
    (
        "contains",
        ("search_contacts", "search_reminder", "search_reminders",
         "search_messages", "search_events", "search_calendar"),
        "look up the specific record the user asked about",
    ),
    (
        "contains",
        ("search_files",),
        "find the files matching the user's search criteria",
    ),
    (
        "contains",
        ("search_content", "search_repositories", "search_code"),
        "search for the content matching the user's query",
    ),
    # --- Generic search (after specific patterns) ---
    (
        "contains",
        ("search",),
        "find the items matching the user's search request",
    ),
    # --- Read operations ---
    (
        "contains",
        ("read_multiple_files", "read_text_file", "read_file"),
        "read the target file to extract the specific content the user needs",
    ),
    # --- Game world: observation ---
    (
        "contains",
        ("look_around", "look_at_object"),
        "observe the specific location or object relevant to the task",
    ),
    (
        "contains",
        ("open_object", "go_to_location"),
        "open or navigate to the target object or location the user specified",
    ),
    # --- Game world: interaction ---
    (
        "contains",
        ("use_object_on_object", "pick_up_object", "pick_up"),
        "interact with the object to accomplish the task goal",
    ),
    # --- Mutation: write ---
    (
        "contains",
        ("write_file",),
        "write the file the user requested with the specified content",
    ),
    # --- CRUD: update / delete (before move — "remove" contains "move") ---
    (
        "contains",
        ("remove", "delete", "cancel", "update", "modify", "edit", "revoke", "archive"),
        "apply the modification the user requested to the target resource",
    ),
    # --- Mutation: create (specific patterns) ---
    (
        "contains",
        ("create_directory", "create_file", "create_issue", "create_repository"),
        "create the resource the user requested",
    ),
    # --- Mutation: move / relocate ---
    (
        "contains",
        ("move_file", "move",),
        "relocate the item to the destination the user specified",
    ),
    # --- Shell / command execution ---
    (
        "contains",
        ("execute_command",),
        "execute the command that directly fulfills the user's request",
    ),
    # --- Database ---
    (
        "exact",
        ("query",),
        "execute the query to retrieve the exact data the user requested",
    ),
    (
        "contains",
        ("sql", "postgres", "database"),
        "run the database query to get the data the user asked for",
    ),
    # --- Browser: navigation (before generic browser_) ---
    (
        "contains",
        ("browser_navigate", "navigate"),
        "navigate to the target page to perform the requested action",
    ),
    # --- Browser: interaction (generic browser_ catch-all) ---
    (
        "contains",
        ("browser_", "click_element", "fill_form", "type_text", "press_key"),
        "perform the browser interaction to complete the user's request",
    ),
    # --- CRUD: create / add (generic) ---
    (
        "contains",
        ("create", "add", "insert", "register", "book", "submit"),
        "create or register the entry the user requested",
    ),
    # --- Read / get (generic catch-all, after specific patterns) ---
    (
        "contains",
        ("get_", "fetch_", "read_", "list_", "lookup_", "retrieve"),
        "retrieve the specific information the user requested to complete the task",
    ),
    # --- Mutation: set / put / post ---
    (
        "contains",
        ("set_", "put_", "post_", "send_", "publish"),
        "apply the change the user requested",
    ),
]

GENERIC_TOOL_INTENT = "perform the operation the user requested to advance the task"
GENERIC_NEXT_STEP_THOUGHT = (
    "I need to take the next action that directly addresses the user's request."
)

DEFAULT_PLAN_WITH_OBJECTIVE_TEMPLATE = (
    "I'll break this task into concrete actions: identify what the user needs, "
    "then execute each step to deliver the result. Goal: {objective}"
)
DEFAULT_PLAN_WITHOUT_OBJECTIVE = (
    "I'll identify the key actions needed and execute them to complete the user's request."
)

DEFAULT_RETRY_THOUGHT = (
    "That call failed, so I'll use the error signal to correct the parameters before retrying."
)
DEFAULT_RETRY_THOUGHT_VARIANTS = (
    "That call failed, so I'll use the error signal to correct the parameters before retrying.",
    "The previous attempt didn't work; I'll tighten the inputs and retry with a concrete fix.",
    "I need to recover from the failed call by correcting the likely argument mismatch, then retry.",
)
DEFAULT_STEP_THOUGHT_VARIANTS = (
    "I need to {intent}.",
    "To complete the user's request, I'll {intent}.",
    "The direct next action is to {intent}.",
    "I should {intent}.",
    "To address the request, I'll {intent}.",
    "The task requires me to {intent}.",
)

DEFAULT_FOCUS_SUFFIX_TEMPLATE = " I'll focus on {focus}."

# Heuristic markers used to detect overly-template fallback traces.
REPEATED_TEMPLATE_PHRASE = (
    "i should first clarify the goal, then execute the tool calls in order"
)
# Note: This phrase is intentionally kept — the old phrase is still useful for detecting
# legacy template traces. New task-execution templates produce diverse, action-specific
# thoughts that won't match either phrase.
