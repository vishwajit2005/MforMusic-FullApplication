package com.mformusic.frontend.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.mformusic.frontend.model.SongResponse
import com.mformusic.frontend.network.PlayerManager
import com.mformusic.frontend.network.RetrofitClient
import kotlinx.coroutines.FlowPreview
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch

@OptIn(FlowPreview::class)
class SearchViewModel : ViewModel() {

    private val _rawQuery = MutableStateFlow("")

    private val _query = MutableStateFlow("")
    val query: StateFlow<String> = _query.asStateFlow()

    private val _suggestions = MutableStateFlow<List<SongResponse>>(emptyList())
    val suggestions: StateFlow<List<SongResponse>> = _suggestions.asStateFlow()

    private val _isLoading = MutableStateFlow(false)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    private val api = RetrofitClient.musicApiService

    init {
        // Debounce search to avoid hammering the API on every keystroke
        viewModelScope.launch {
            _rawQuery
                .debounce(400L)
                .distinctUntilChanged()
                .collect { q ->
                    _query.value = q
                    if (q.isBlank()) {
                        _suggestions.value = emptyList()
                        _isLoading.value = false
                    } else {
                        fetchSuggestions(q)
                    }
                }
        }
    }

    fun updateQuery(query: String) {
        _rawQuery.value = query
    }

    private suspend fun fetchSuggestions(query: String) {
        _isLoading.value = true
        _error.value = null
        try {
            val response = api.getSearchSuggestions(query)
            if (response.isSuccessful) {
                _suggestions.value = response.body() ?: emptyList()
            } else {
                _error.value = "Search failed"
            }
        } catch (e: Exception) {
            _error.value = "Could not connect to server"
        } finally {
            _isLoading.value = false
        }
    }

    /**
     * Play [song] from the current search results and set the full results list
     * as the active queue so that next / previous buttons navigate through
     * all search results.
     *
     * The clicked song's URL is resolved via the play API. All other results
     * use their stored saavnUrl so they can be played immediately without extra
     * network calls.
     */
    fun playSong(song: SongResponse) {
        viewModelScope.launch {
            try {
                val response = api.playOrCacheSong(song.title)
                if (response.isSuccessful && response.body() != null) {
                    val resolvedSong = response.body()!!
                    val resolvedUrl  = resolvedSong.s3Url ?: resolvedSong.saavnUrl

                    // Build queue from the current suggestion list, replacing
                    // the clicked entry with the freshly-resolved song metadata.
                    val currentList = _suggestions.value
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
