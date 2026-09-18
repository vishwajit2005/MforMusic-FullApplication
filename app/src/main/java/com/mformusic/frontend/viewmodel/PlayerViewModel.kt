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
import kotlinx.coroutines.Job
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.distinctUntilChanged

/**
 * ViewModel wrapping PlayerManager state, database persistence, download manager, and telemetry.
 * Exposes player state to Compose UI and survives recomposition.
 */
class PlayerViewModel(application: Application) : AndroidViewModel(application) {

    data class SimilarSongsState(
        val loading: Boolean = false,
        val songs: List<SongResponse> = emptyList(),
        val error: String? = null,
        val playingId: String? = null
    )
    private val _similarSongs = MutableStateFlow(SimilarSongsState())
    val similarSongs: StateFlow<SimilarSongsState> = _similarSongs.asStateFlow()
    private var similarJob: Job? = null

    fun loadSimilarSongs() {
        val id = currentTrack.value?.externalTrackId ?: return
        similarJob?.cancel()
        _similarSongs.value = SimilarSongsState(loading = true)
        similarJob = viewModelScope.launch {
            try {
                val context = PlayerManager.recentContextFor(id)
                if (currentTrack.value?.externalTrackId != id) return@launch
                val response = api.getSimilarSongs(id, context)
                if (currentTrack.value?.externalTrackId != id) return@launch
                _similarSongs.value = if (response.isSuccessful) {
                    SimilarSongsState(songs = response.body().orEmpty())
                } else SimilarSongsState(error = "Couldn't load similar songs. Please try again.")
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                if (currentTrack.value?.externalTrackId == id) {
                    _similarSongs.value = SimilarSongsState(error = "Couldn't connect. Please try again.")
                }
            }
        }
    }

    fun playSimilarSong(song: SongResponse) {
        if (_similarSongs.value.playingId != null) return
        val sourceId = currentTrack.value?.externalTrackId
        _similarSongs.value = _similarSongs.value.copy(playingId = song.externalTrackId, error = null)
        viewModelScope.launch {
            try {
                val response = api.playSongById(song.externalTrackId)
                if (currentTrack.value?.externalTrackId != sourceId) return@launch
                val resolved = response.body()
                if (!response.isSuccessful || resolved == null || resolved.externalTrackId != song.externalTrackId) {
                    _similarSongs.value = _similarSongs.value.copy(error = "Couldn't play this song. Try again.")
                    return@launch
                }
                val queue = _similarSongs.value.songs.map { if (it.externalTrackId == resolved.externalTrackId) resolved else it }
                val index = queue.indexOfFirst { it.externalTrackId == resolved.externalTrackId }
                if (index >= 0) PlayerManager.setQueueAndPlay(
                    queue.map { it to (it.s3Url?.takeIf(String::isNotBlank) ?: it.saavnUrl) }, index)
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                if (currentTrack.value?.externalTrackId == sourceId) {
                    _similarSongs.value = _similarSongs.value.copy(error = "Couldn't play this song. Try again.")
                }
            } finally {
                _similarSongs.value = _similarSongs.value.copy(playingId = null)
            }
        }
    }

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
        viewModelScope.launch {
            currentTrack.map { it?.externalTrackId }.distinctUntilChanged().collect {
                similarJob?.cancel()
                _similarSongs.value = SimilarSongsState()
            }
        }
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