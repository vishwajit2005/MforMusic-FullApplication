package com.mformusic.frontend.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.mformusic.frontend.model.SongResponse
import com.mformusic.frontend.network.PlayerManager
import com.mformusic.frontend.network.RetrofitClient
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class HomeViewModel : ViewModel() {

    private val _recentSongs = MutableStateFlow<List<SongResponse>>(emptyList())
    val recentSongs: StateFlow<List<SongResponse>> = _recentSongs.asStateFlow()

    private val _isLoading = MutableStateFlow(true)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    private val api = RetrofitClient.musicApiService

    init {
        fetchRecentSongs()
    }

    fun fetchRecentSongs() {
        viewModelScope.launch {
            _isLoading.value = true
            _error.value = null
            try {
                val response = api.getRecentSongs()
                if (response.isSuccessful) {
                    _recentSongs.value = response.body() ?: emptyList()
                } else {
                    _error.value = "Failed to load recent songs"
                }
            } catch (e: Exception) {
                _error.value = "Could not connect to server"
            } finally {
                _isLoading.value = false
            }
        }
    }

    /**
     * Play [song] and set the full recently-played list as the active queue so
     * that next / previous buttons work across all recent songs.
     *
     * The clicked song's URL is resolved via the play API (bumps play-count /
     * caches to S3). All other recent songs use their stored saavnUrl so they
     * can play immediately without extra API calls.
     */
    fun playSong(song: SongResponse) {
        viewModelScope.launch {
            try {
                val response = api.playOrCacheSong(song.title)
                if (response.isSuccessful && response.body() != null) {
                    val resolvedSong = response.body()!!
                    val resolvedUrl  = resolvedSong.s3Url ?: resolvedSong.saavnUrl

                    // Refresh recent-songs list after play (play-count changed)
                    fetchRecentSongs()

                    // Build queue from the list that was loaded before the refresh;
                    // replace the clicked song with its freshly-resolved version.
                    val currentList = _recentSongs.value
                    val updatedList = currentList.map { s ->
                        if (s.externalTrackId == resolvedSong.externalTrackId) resolvedSong else s
                    }

                    val clickedIndex = updatedList.indexOfFirst {
                        it.externalTrackId == resolvedSong.externalTrackId
                    }.coerceAtLeast(0)

                    val queueEntries = updatedList.map { s ->
                        s to (s.s3Url ?: s.saavnUrl)
                    }

                    PlayerManager.setQueueAndPlay(queueEntries, clickedIndex)
                } else {
                    _error.value = "Playback failed. Try again."
                }
            } catch (e: Exception) {
                _error.value = "Playback error: ${e.message}"
            }
        }
    }

    fun clearError() { _error.value = null }
}
