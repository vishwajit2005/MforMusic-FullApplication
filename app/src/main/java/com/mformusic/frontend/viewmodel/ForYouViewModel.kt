package com.mformusic.frontend.viewmodel

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.mformusic.frontend.model.SongResponse
import com.mformusic.frontend.network.PlayerManager
import com.mformusic.frontend.network.RetrofitClient
import com.mformusic.frontend.worker.PredictiveCacheWorker
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/** States for the "For You" personalised feed */
sealed interface ForYouUiState {
    /** Initial load in progress */
    object Loading : ForYouUiState
    /** Recommendations loaded (list may be empty — user in cold start) */
    data class Success(val songs: List<SongResponse>) : ForYouUiState
    /** FastAPI/Spring Boot unreachable */
    data class Error(val message: String) : ForYouUiState
}

class ForYouViewModel(application: Application) : AndroidViewModel(application) {

    private val _uiState = MutableStateFlow<ForYouUiState>(ForYouUiState.Loading)
    val uiState: StateFlow<ForYouUiState> = _uiState.asStateFlow()

    private val _isRefreshing = MutableStateFlow(false)
    val isRefreshing: StateFlow<Boolean> = _isRefreshing.asStateFlow()

    private val api = RetrofitClient.musicApiService

    init {
        fetchRecommendations()
    }

    fun fetchRecommendations(n: Int = 20) {
        viewModelScope.launch {
            _isRefreshing.value = true
            if (_uiState.value !is ForYouUiState.Success) {
                _uiState.value = ForYouUiState.Loading
            }
            try {
                val response = api.getRecommendations(n)
                if (response.isSuccessful) {
                    val songs = response.body() ?: emptyList()
                    _uiState.value = ForYouUiState.Success(songs)
                    // Kick off background pre-caching on WiFi (Phase 5)
                    if (songs.isNotEmpty()) {
                        PredictiveCacheWorker.enqueue(getApplication())
                    }
                } else {
                    _uiState.value = ForYouUiState.Error("Unable to load recommendations (${response.code()})")
                }
            } catch (e: Exception) {
                _uiState.value = ForYouUiState.Error("Could not connect to server")
            } finally {
                _isRefreshing.value = false
            }
        }
    }

    /**
     * Plays the tapped song and sets the entire recommendation list as the
     * active queue so next/previous buttons work across the full "For You" feed.
     */
    fun playSong(song: SongResponse) {
        viewModelScope.launch {
            try {
                val response = api.playOrCacheSong(song.title)
                if (response.isSuccessful && response.body() != null) {
                    val resolved = response.body()!!

                    // Rebuild the queue with the freshly-resolved song URL
                    val currentList = (_uiState.value as? ForYouUiState.Success)?.songs ?: listOf(resolved)
                    val updatedList = currentList.map { s ->
                        if (s.externalTrackId == resolved.externalTrackId) resolved else s
                    }
                    val clickedIndex = updatedList
                        .indexOfFirst { it.externalTrackId == resolved.externalTrackId }
                        .coerceAtLeast(0)

                    val queueEntries = updatedList.map { s -> s to (s.s3Url ?: s.saavnUrl) }
                    PlayerManager.setQueueAndPlay(queueEntries, clickedIndex)
                }
            } catch (e: Exception) {
                // Swallow silently — playback errors are shown by the player component
            }
        }
    }
}
