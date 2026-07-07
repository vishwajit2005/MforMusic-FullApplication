# MforMusic 🎵

MforMusic is a full-stack, cloud-cached music streaming application. It features a native **Android client** (Kotlin, Jetpack Compose, Jetpack Media3) and a **Spring Boot backend** (Java 17, Spring Security with JWT, MySQL, and Supabase Storage). 

The application utilizes a **hybrid streaming, caching, and LRU eviction architecture** to stream audio tracks dynamically from external CDNs, cache them in private cloud storage, and support full offline playback on mobile devices.

---

## 🚀 Key Features

*   **Hybrid Streaming & Cloud Caching**: Resolves requested tracks dynamically from JioSaavn CDN, serving them instantly to the client while running an asynchronous background upload to Supabase Storage.
*   **OOM-Safe Direct Chunk-Streaming**: Streams bytes directly from external CDNs to cloud storage using a memory-efficient 8KB chunk buffer, preventing JVM Out Of Memory (OOM) errors in low-resource environments.
*   **LRU Cache Eviction Policy**: Automatically evicts the 10 least-played (and oldest-played) tracks from Supabase Storage when the storage cap (`550` tracks) is reached, containing private storage costs.
*   **Jetpack Media3 & Background Playback**: Leverages Android `MediaSessionService` for lockscreen integration, notification playback controls, audio focus handling (ducking for calls), and output redirection (pause on headphone unplug).
*   **Full Offline Support**: Allows downloading tracks to local storage. It caches metadata in a local SQLite database (Room DB) and switches to file-system URIs (`file:///...`) for zero-network playback.
*   **Stateless Security**: Fully secured via Spring Security with JWT and salted password hashing (BCrypt). Mobile clients utilize a Retrofit interceptor to inject active session tokens saved in Jetpack DataStore.

---

## 🛠️ Technology Stack

| Component | Technology | Description |
| :--- | :--- | :--- |
| **Frontend** | Kotlin, Jetpack Compose | Modern UI framework with custom components & transitions |
| **Media Engine** | Jetpack Media3 (ExoPlayer) | Seamless streaming, caching, and background playback |
| **Local Storage** | Room DB, DataStore | Local SQLite database & secure preferences storage |
| **Networking** | Retrofit, OkHttp | REST API client & connection interceptors |
| **Backend** | Java 17, Spring Boot | Web API, REST controllers, and Async services |
| **Security** | Spring Security, JWT, BCrypt | Token-based stateless authentication & password hashing |
| **Database** | MySQL (Aiven Cloud), JPA/Hibernate | Primary relational storage & ORM mapping |
| **Cloud Storage** | Supabase Storage (S3-compatible) | Private hosting bucket for cached audio files |
| **Deployment** | Docker, Multi-stage builds | Production containerization |

---

## 📂 Project Structure

```
MforMusic/
├── app/                        # Android Client (Kotlin)
│   ├── src/main/java/          # Source files (ViewModels, UI, Networking, Local DB)
│   ├── src/main/res/           # Asset files (Drawables, Colors, Themes)
│   └── build.gradle.kts        # Android build configuration
├── backend/                    # Spring Boot REST API (Java)
│   ├── src/main/java/          # REST Controllers, Models, Services, Repositories
│   ├── src/main/resources/     # Application configuration properties
│   ├── Dockerfile              # Multi-stage production Docker build configuration
│   └── pom.xml                 # Maven dependency descriptor
├── build.gradle.kts            # Project-level Gradle build configuration
└── settings.gradle.kts         # Gradle project modular configurations
```

---

## ⚙️ Configuration & Environment Variables

### Backend Configuration
The backend requires several environment variables to run. In local development, these can be set in an IDE configuration or loaded from the environment:

| Variable | Description | Example / Default |
| :--- | :--- | :--- |
| `DB_HOST` | MySQL hostname (Aiven cloud or local) | `mysql-xxxxx.aivencloud.com` |
| `DB_PORT` | MySQL connection port | `22486` |
| `DB_NAME` | MySQL database name | `mformusic_db` |
| `DB_USER` | MySQL username | `avnadmin` |
| `DB_PASSWORD` | MySQL password | `your_secure_password` |
| `JWT_SECRET` | Secret key for signing tokens (min 32 chars) | `your_random_jwt_secret_string` |
| `SUPABASE_URL` | Supabase project URL | `https://xxxx.supabase.co` |
| `SUPABASE_ANON_KEY` | Supabase public/anonymous API key | `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...` |
| `SUPABASE_BUCKET` | Supabase storage bucket name | `tracks` (defaults to `tracks`) |
| `PORT` | Web server port | `8080` (defaults to `8080`) |

### Frontend Configuration
Configure the server URL by updating `app/build.gradle.kts`:
```kotlin
buildTypes {
    release {
        buildConfigField("String", "BASE_URL", "\"https://mformusic-api-production.up.railway.app/\"")
    }
    debug {
        buildConfigField("String", "BASE_URL", "\"http://10.0.2.2:8080/\"") // Points to localhost in Android Emulator
    }
}
```

---

## 🏃 Getting Started

### Running the Backend

#### Option 1: Locally with Maven
Ensure you have **Java 17+** and **Maven 3.9+** installed:
1. Navigate to the backend directory:
   ```bash
   cd backend
   ```
2. Export your environment variables:
   ```bash
   export DB_HOST=localhost DB_PORT=3306 DB_NAME=mformusic_db DB_USER=root DB_PASSWORD=secret JWT_SECRET=mysecret SUPABASE_URL=url SUPABASE_ANON_KEY=key
   ```
3. Run the Spring Boot application:
   ```bash
   ./mvnw spring-boot:run
   ```

#### Option 2: Running with Docker
A multi-stage `Dockerfile` is provided in the `backend/` directory for containerization.
1. Build the Docker image:
   ```bash
   docker build -t mformusic-backend ./backend
   ```
2. Start the container (injecting your environment variables):
   ```bash
   docker run -d -p 8080:8080 \
     -e DB_HOST=host \
     -e DB_PORT=port \
     -e DB_NAME=dbname \
     -e DB_USER=user \
     -e DB_PASSWORD=pwd \
     -e JWT_SECRET=secret \
     -e SUPABASE_URL=url \
     -e SUPABASE_ANON_KEY=key \
     mformusic-backend
   ```

### Running the Frontend (Android Client)
1. Open the project root `MforMusic/` folder in **Android Studio**.
2. Sync the project with Gradle files.
3. Configure your API base URL (in `app/build.gradle.kts` `buildTypes`).
4. Build the application and run it on an Android Emulator or a physical device.

---

## 🔒 Security
Authentication is stateless and handled via JWT:
- New users register at `/api/v1/auth/register` (passwords hashed using BCrypt).
- Logging in via `/api/v1/auth/login` returns a JWT token containing authenticated session claims.
- The Android client intercepts all API calls via Retrofit and injects the `Authorization: Bearer <token>` header dynamically.

---

## 📄 License
This project is licensed under the MIT License - see the LICENSE file for details.
