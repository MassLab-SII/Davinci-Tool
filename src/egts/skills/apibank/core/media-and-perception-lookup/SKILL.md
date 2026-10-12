# Media And Perception Lookup

## Description

Use API-Bank's local media perception tools for image caption lookup, speech recognition lookup, music playback URL generation, and follow-up search.

## Use Cases

- Get a caption for a known image URL
- Transcribe known audio through speech recognition lookup
- Generate a music playback URL for a requested song
- Search related information after media lookup

## Workflow

### Step 1: Discover media APIs
- **Tool**: `ToolSearcher`
- **Example**: `ToolSearcher({"keywords": "image caption speech recognition music"})`
- **Purpose**: Ground the media workflow in available API-Bank tools.

### Step 2: Caption image
- **Tool**: `ImageCaption` × 1-n times
- **Example**: `ImageCaption({"url": "https://example.com/image.jpg"})`
- **Purpose**: Retrieve local caption evidence for an image URL known to the API-Bank database.

### Step 3: Recognize speech
- **Tool**: `SpeechRecognition` × 1-n times
- **Example**: `SpeechRecognition({"url": "https://example.com/audio.wav"})`
- **Purpose**: Retrieve local speech transcription evidence.

### Step 4: Play music
- **Tool**: `PlayMusic`
- **Example**: `PlayMusic({"music_name": "Imagine"})`
- **Purpose**: Generate a playback URL scheme for a requested song.

### Step 5: Search follow-up context
- **Tool**: `SearchEngine` × 1-n times
- **Example**: `SearchEngine({"keyword": "song Imagine"})`
- **Purpose**: Connect media lookup to broader information retrieval when useful.

### Step 6: Verify or compare outputs
- **Tool**: `ImageCaption` or `SpeechRecognition` × 1-n times
- **Example**: `SpeechRecognition({"url": "https://example.com/audio.wav"})`
- **Purpose**: Repeat lookup or compare media items to produce deeper retrieval trajectories.

## Tools Involved

`ToolSearcher`, `ImageCaption`, `SpeechRecognition`, `PlayMusic`, `SearchEngine`

## Tips

- Image and audio tools are local lookups; use URLs that are likely present in API-Bank data.
- `PlayMusic` returns a URL scheme rather than changing user calendar state.
- Use follow-up search to turn simple perception calls into richer evidence chains.
