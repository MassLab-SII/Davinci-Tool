# Movie Preference Recommendation

## Description

Build movie recommendations by retrieving a user's preference categories, checking watched movie history, and requesting recommendations from preference labels. This skill covers Level-3 entertainment recommendation workflows.

## Use Cases

- Recommend movies based on a user's known preferences
- Compare watched movies with recommended movies
- Retrieve preference evidence before calling recommendation APIs
- Produce candidate watch lists for a named user

## Workflow

### Step 1: Discover movie APIs
- **Tool**: `Lv3ToolSearcher`
- **Example**: `Lv3ToolSearcher({"keywords": "movie preferences watched recommendation"})`
- **Purpose**: Identify the movie preference, watched-history, and recommendation APIs.

### Step 2: Retrieve user preferences
- **Tool**: `UserMoviePreferences`
- **Example**: `UserMoviePreferences({"user_name": "John"})`
- **Purpose**: Get preference categories such as `Action`, `Comedy`, or `Drama`.

### Step 3: Retrieve watched movies
- **Tool**: `UserWatchedMovies`
- **Example**: `UserWatchedMovies({"user_name": "John"})`
- **Purpose**: Ground recommendations against movies the user has already watched.

### Step 4: Generate recommendations
- **Tool**: `MovieRecommendations`
- **Example**: `MovieRecommendations({"preferences": ["Action", "Comedy"]})`
- **Purpose**: Retrieve candidate movies for the preference categories.

### Step 5: Explore another user or preference subset
- **Tool**: `UserMoviePreferences` or `MovieRecommendations` × 1-n times
- **Examples**:
  - `UserMoviePreferences({"user_name": "Mary"})`
  - `MovieRecommendations({"preferences": ["Romance", "Drama"]})`
- **Purpose**: Compare users or refine recommendations by trying different preference subsets.

## Tools Involved

`Lv3ToolSearcher`, `UserMoviePreferences`, `UserWatchedMovies`, `MovieRecommendations`

## Tips

- Use seeded users such as `John`, `Mary`, `Peter`, `Tom`, and `Jerry`.
- `MovieRecommendations` expects a list of genre strings.
- Use watched history as evidence to avoid recommending only already-watched items in downstream synthesis.

