package com.mformusic.frontend.viewmodel

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.mformusic.frontend.data.TokenDataStore
import com.mformusic.frontend.data.local.AppDatabase
import com.mformusic.frontend.data.repository.DownloadRepository
import com.mformusic.frontend.model.SongResponse
import com.mformusic.frontend.network.PlayerManager
import com.mformusic.frontend.network.RetrofitClient
import com.mformusic.frontend.telemetry.InteractionType
import com.mformusic.frontend.telemetry.SessionManager
import com.mformusic.frontend.telemetry.TelemetryEvent
import com.mformusic.frontend.telemetry.TelemetryRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch

/**
 * ViewModel wrapping PlayerManager state, database persistence, download manager, and telemetry.
 * Exposes player state to Compose UI and survives recomposition.
 */
class PlayerViewModel(application: Application) : AndroidViewModel(application) {

    private val api = RetrofitClient.musicApiService
    private val db = AppDatabase.getDatabase(application)
    private val dao = db.downloadedSongDao()
    private val tokenDataStore = TokenDataStore(application.applicationContext)

    private var currentUserId: String = ""

    val isPlaying: StateFlow<Boolean> = PlayerManager.isPlaying
    val currentTrack: StateFlow<SongResponse?> = PlayerManager.currentTrack
    val currentTrackTitle: StateFlow<String?> = PlayerManager.currentTrackTitle
    val currentArtistName: StateFlow<String?> = PlayerManager.currentArtistName
    val currentAlbumArt: StateFlow<String?> = PlayerManager.currentAlbumArt
    val currentPosition: StateFlow<Long> = PlayerManager.currentPosition
    val duration: StateFlow<Long> = PlayerManager.duration

    // ── Shuffle / Repeat ──────────────────────────────────────────────────────
    val isShuffleOn: StateFlow<Boolean> = PlayerManager.isShuffleOn
    val repeatMode: StateFlow<PlayerManager.RepeatMode> = PlayerManager.repeatMode

    // Track if current track is downloaded
    private val _isDownloaded = MutableStateFlow(false)
    val isDownloaded: StateFlow<Boolean> = _isDownloaded.asStateFlow()

    // Track if current track is downloading
    private val _isDownloading = MutableStateFlow(false)
    val isDownloading: StateFlow<Boolean> = _isDownloading.asStateFlow()

    init {
        // Load userId asynchronously for telemetry
        viewModelScope.launch {
            currentUserId = tokenDataStore.getUserId()?.toString() ?: ""
        }

        // Observe currentTrack to check download state
        viewModelScope.launch {
            currentTrack.collectLatest { track ->
                if (track != null) {
                    dao.getDownloadedSongFlow(track.externalTrackId).collectLatest { localSong ->
                        _isDownloaded.value = localSong != null
                    }
                } else {
                    _isDownloaded.value = false
                }
            }
        }

        // Observe downloading set
        viewModelScope.launch {
            DownloadRepository.downloadingTracks.collectLatest { downloadingSet ->
                val track = currentTrack.value
                _isDownloading.value = track != null && downloadingSet.contains(track.externalTrackId)
            }
        }
    }

    fun togglePlayPause() = PlayerManager.togglePlayPause()

    fun seekTo(positionMs: Long) = PlayerManager.seekTo(positionMs)

    fun skipToNext() = PlayerManager.skipToNext()

    fun skipToPrevious() = PlayerManager.skipToPrevious()

    fun toggleShuffle() = PlayerManager.toggleShuffle()

    fun cycleRepeatMode() = PlayerManager.cycleRepeatMode()

    fun toggleLike() {
        val song = currentTrack.value ?: return
        val songId = song.id ?: return

        viewModelScope.launch {
            try {
                val response = if (song.liked) {
                    api.unlikeSong(songId)
                } else {
                    api.likeSong(songId)
                }
                if (response.isSuccessful && response.body() != null) {
                    val updatedSong = response.body()!!
                    PlayerManager.setCurrentTrackLiked(updatedSong.liked)

                    // Ensure userId is populated
                    if (currentUserId.isBlank()) {
                        currentUserId = tokenDataStore.getUserId()?.toString() ?: ""
                    }

                    TelemetryRepository.enqueue(
                        TelemetryEvent(
                            userId = currentUserId,
                            songId = song.externalTrackId,
                            interactionType = if (!song.liked) InteractionType.LIKE.name.lowercase() else InteractionType.UNLIKE.name.lowercase(),
                            sessionId = SessionManager.sessionId
                        )
                    )
                }
            } catch (e: Exception) {
                // Silently ignore telemetry failure
            }
        }
    }

    fun toggleDownload() {
        val song = currentTrack.value ?: return
        viewModelScope.launch {
            if (_isDownloaded.value) {
                DownloadRepository.deleteSong(getApplication(), song.externalTrackId)
                _isDownloaded.value = false
            } else {
                val success = DownloadRepository.downloadSong(getApplication(), song)
                if (success) {
                    _isDownloaded.value = true

                    // Ensure userId is populated
                    if (currentUserId.isBlank()) {
                        currentUserId = tokenDataStore.getUserId()?.toString() ?: ""
                    }

                    TelemetryRepository.enqueue(
                        TelemetryEvent(
                            userId = currentUserId,
                            songId = song.externalTrackId,
                            interactionType = InteractionType.DOWNLOAD.name.lowercase(),
                            sessionId = SessionManager.sessionId
                        )
                    )
                }
            }
        }
    }
}