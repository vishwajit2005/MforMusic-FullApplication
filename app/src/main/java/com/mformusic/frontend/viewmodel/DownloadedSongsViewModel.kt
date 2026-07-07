package com.mformusic.frontend.viewmodel

import android.app.Application
import android.net.Uri
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.mformusic.frontend.data.local.AppDatabase
import com.mformusic.frontend.data.local.DownloadedSong
import com.mformusic.frontend.data.repository.DownloadRepository
import com.mformusic.frontend.model.SongResponse
import com.mformusic.frontend.network.PlayerManager
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch
import java.io.File

class DownloadedSongsViewModel(application: Application) : AndroidViewModel(application) {

    private val db  = AppDatabase.getDatabase(application)
    private val dao = db.downloadedSongDao()

    private val _downloadedSongs = MutableStateFlow<List<DownloadedSong>>(emptyList())
    val downloadedSongs: StateFlow<List<DownloadedSong>> = _downloadedSongs.asStateFlow()

    private val _isLoading = MutableStateFlow(true)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    init {
        fetchDownloadedSongs()
    }

    fun fetchDownloadedSongs() {
        viewModelScope.launch {
            _isLoading.value = true
            try {
                dao.getAllDownloadedSongs().collectLatest { songs ->
                    _downloadedSongs.value = songs
                    _isLoading.value = false
                }
            } catch (e: Exception) {
                _isLoading.value = false
            }
        }
    }

    /**
     * Play [song] and set the full downloaded list as the active queue so
     * that next / previous buttons work across all downloaded songs.
     * Each song uses its local file URI for offline playback.
     */
    fun playSong(song: DownloadedSong) {
        val songs = _downloadedSongs.value

        // Build the queue: every downloaded song uses its local file path as the URL.
        val queueEntries = songs.map { s ->
            val songResponse = SongResponse(
                id                = null,
                externalTrackId   = s.externalTrackId,
                title             = s.title,
                artistName        = s.artistName,
                durationInSeconds = s.durationInSeconds,
                thumbnailUrl      = s.thumbnailUrl,
                s3Url             = s.s3Url,
                saavnUrl          = s.saavnUrl,
                playCount         = 0,
                isStoredInS3      = s.s3Url != null,
                liked             = false
            )
            val localUri = Uri.fromFile(File(s.localFilePath)).toString()
            songResponse to localUri
        }

        val clickedIndex = songs.indexOfFirst { it.externalTrackId == song.externalTrackId }
            .coerceAtLeast(0)

        PlayerManager.setQueueAndPlay(queueEntries, clickedIndex)
    }

    /** Delete a downloaded song from the local database and filesystem. */
    fun deleteSong(song: DownloadedSong) {
        viewModelScope.launch {
            try {
                DownloadRepository.deleteSong(getApplication(), song.externalTrackId)
                _downloadedSongs.value = _downloadedSongs.value.filter {
                    it.externalTrackId != song.externalTrackId
                }
            } catch (e: Exception) {
                _error.value = "Failed to delete: ${e.message}"
            }
        }
    }

    /** Reorder songs by moving [from] index to [to] index (in-memory only). */
    fun reorderSongs(from: Int, to: Int) {
        val list = _downloadedSongs.value.toMutableList()
        if (from < 0 || to < 0 || from >= list.size || to >= list.size) return
        val item = list.removeAt(from)
        list.add(to, item)
        _downloadedSongs.value = list
    }

    fun clearError() { _error.value = null }
}
