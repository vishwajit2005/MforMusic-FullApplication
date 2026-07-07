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

class LikedSongsViewModel : ViewModel() {

    private val _likedSongs = MutableStateFlow<List<SongResponse>>(emptyList())
    val likedSongs: StateFlow<List<SongResponse>> = _likedSongs.asStateFlow()

    private val _isLoading = MutableStateFlow(true)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    private val api = RetrofitClient.musicApiService

    init {
        fetchLikedSongs()
    }

    fun fetchLikedSongs() {
        viewModelScope.launch {
            _isLoading.value = true
            _error.value = null
            try {
                val response = api.getLikedSongs()
                if (response.isSuccessful) {
                    _likedSongs.value = response.body() ?: emptyList()
                } else {
                    _error.value = "Failed to load liked songs"
                }
            } catch (e: Exception) {
                _error.value = "Could not connect to server"
            } finally {
                _isLoading.value = false
            }
        }
    }

    /**
     * Play [song] and set the full liked-songs list as the active queue so
     * that next / previous buttons work across all liked songs.
     *
     * The clicked song's URL is resolved via the play API (which also bumps
     * play-count and caches to S3 if needed). All other songs in the queue
     * use their stored saavnUrl as a fallback so they can play immediately
     * without extra API calls.
     */
    fun playSong(song: SongResponse) {
        viewModelScope.launch {
            try {
                // Resolve the selected song's best stream URL
                val response = api.playOrCacheSong(song.title)
                if (response.isSuccessful && response.body() != null) {
                    val resolvedSong = response.body()!!
                    val resolvedUrl  = resolvedSong.s3Url ?: resolvedSong.saavnUrl

                    // Build queue: use the resolved song for the clicked position;
                    // use stored saavnUrl / s3Url for every other song in the list.
                    val currentList = _likedSongs.value

                    // Update the clicked song in our local list with the resolved metadata
                    val updatedList = currentList.map { s ->
                        if (s.externalTrackId == song.externalTrackId) resolvedSong else s
                    }
                    _likedSongs.value = updatedList

                    val clickedIndex = updatedList.indexOfFirst {
                        it.externalTrackId == resolvedSong.externalTrackId
                    }.coerceAtLeast(0)

                    // Each song in the queue uses its best available URL.
                    // saavnUrl is always non-empty per the data model.
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

    /** Unlike (remove) a song from the liked playlist. */
    fun removeSong(song: SongResponse) {
        val songId = song.id ?: return
        viewModelScope.launch {
            try {
                val response = api.unlikeSong(songId)
                if (response.isSuccessful) {
                    _likedSongs.value = _likedSongs.value.filter {
                        it.externalTrackId != song.externalTrackId
                    }
                } else {
                    _error.value = "Failed to remove song"
                }
            } catch (e: Exception) {
                _error.value = "Error removing song: ${e.message}"
            }
        }
    }

    /** Reorder songs by moving [from] index to [to] index (in-memory only). */
    fun reorderSongs(from: Int, to: Int) {
        val list = _likedSongs.value.toMutableList()
        if (from < 0 || to < 0 || from >= list.size || to >= list.size) return
        val item = list.removeAt(from)
        list.add(to, item)
        _likedSongs.value = list
    }

    fun clearError() { _error.value = null }
}
