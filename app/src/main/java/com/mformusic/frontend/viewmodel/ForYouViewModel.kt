package com.mformusic.frontend.viewmodel

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.mformusic.frontend.model.SongResponse
import com.mformusic.frontend.network.PlayerManager
import com.mformusic.frontend.network.RetrofitClient
import com.mformusic.frontend.network.playExact
import com.mformusic.frontend.worker.PredictiveCacheWorker
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import com.mformusic.frontend.BuildConfig
import com.mformusic.frontend.data.RecommendationStore
import com.mformusic.frontend.data.TokenDataStore
import com.mformusic.frontend.data.dataStore
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.Job
import kotlinx.coroutines.CancellationException
import com.mformusic.frontend.network.RecommendationRecovery

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

    private var fetchJob: Job? = null
    private val _waitingForService = MutableStateFlow(false)
    val waitingForService = _waitingForService.asStateFlow()

    private val api = RetrofitClient.musicApiService
    private val tokens = TokenDataStore(application)
    private val savedFeed = RecommendationStore(application.dataStore, BuildConfig.BASE_URL)
    private var accountId: Long? = null
    private val _connectionMessage = MutableStateFlow<String?>(null)
    val connectionMessage = _connectionMessage.asStateFlow()

    init {
        viewModelScope.launch {
            tokens.userIdFlow.distinctUntilChanged().collect { id ->
                fetchJob?.cancel()
                fetchJob?.join()
                accountId = id
                _uiState.value = ForYouUiState.Loading
                _connectionMessage.value = null
                if (id != null) fetchRecommendations()
            }
        }
    }

    fun fetchRecommendations(n: Int = 20) {
        val userId = accountId ?: return
        if (fetchJob?.isActive == true) return
        fetchJob = viewModelScope.launch {
            _waitingForService.value = true
            _isRefreshing.value = true
            _connectionMessage.value = "Connecting… Updating your recommendations."
            if (_uiState.value !is ForYouUiState.Success) {
                _uiState.value = ForYouUiState.Loading
            }
            try {
                if ((_uiState.value as? ForYouUiState.Success)?.songs.isNullOrEmpty()) {
                    val cached = try { savedFeed.read(userId) }
                    catch (e: CancellationException) { throw e }
                    catch (_: Exception) { emptyList() }
                    if (cached.isNotEmpty()) _uiState.value = ForYouUiState.Success(cached)
                }
                if ((_uiState.value as? ForYouUiState.Success)?.songs?.isNotEmpty() == true)
                    _connectionMessage.value = "Connecting… Showing your last saved recommendations."
                val response = RecommendationRecovery.load(
                    onWaiting = { _waitingForService.value = true }
                ) { api.getRecommendations(n) }
                if (response.isSuccessful) {
                    val rawSongs = response.body() ?: emptyList()
                    val songs = rawSongs.distinctBy { it.externalTrackId ?: it.id.toString() }
                    if (songs.isNotEmpty() || (_uiState.value as? ForYouUiState.Success)?.songs.isNullOrEmpty()) {
                        _uiState.value = ForYouUiState.Success(songs)
                        _connectionMessage.value = null
                    } else {
                        _connectionMessage.value = "No new picks yet. Showing your last saved recommendations."
                    }
                    // Kick off background pre-caching on WiFi (Phase 5)
                    if (songs.isNotEmpty()) {
                        try { savedFeed.save(userId, songs) }
                        catch (e: CancellationException) { throw e }
                        catch (_: Exception) { /* A disk failure must not hide a successful response. */ }
                        PredictiveCacheWorker.enqueue(getApplication())
                    }
                } else {
                    showFailure(if (response.code() in listOf(401, 403))
                        "Please sign in again to refresh your recommendations."
                        else "Couldn't refresh recommendations. Please retry.")
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                showFailure("Couldn't connect. Please retry shortly.")
            } finally {
                _isRefreshing.value = false
                _waitingForService.value = false
            }
        }
    }

    private fun showFailure(message: String) {
        if ((_uiState.value as? ForYouUiState.Success)?.songs?.isNotEmpty() == true) {
            _connectionMessage.value = "$message Showing your last saved recommendations."
        } else {
            _connectionMessage.value = null
            _uiState.value = ForYouUiState.Error(message)
        }
    }

    /**
     * Plays the tapped song and sets the entire recommendation list as the
     * active queue so next/previous buttons work across the full "For You" feed.
     */
    fun playSong(song: SongResponse) {
        viewModelScope.launch {
            try {
                val response = api.playExact(song)
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
