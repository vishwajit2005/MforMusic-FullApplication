package com.mformusic.frontend.network

import android.content.Context
import android.net.Uri
import android.os.Handler
import android.os.Looper
import androidx.annotation.OptIn
import androidx.media3.common.MediaItem
import androidx.media3.common.MediaMetadata
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.ExoPlayer
import com.mformusic.frontend.model.SongResponse
import com.mformusic.frontend.telemetry.PlaybackTelemetryListener
import com.mformusic.frontend.telemetry.TelemetryRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

object PlayerManager {

    // ── Telemetry ─────────────────────────────────────────────────────────────
    var telemetryListener: PlaybackTelemetryListener? = null
        private set

    private var exoPlayer: ExoPlayer? = null

    // ── Playback state ─────────────────────────────────────────────────────────
    private val _isPlaying = MutableStateFlow(false)
    val isPlaying: StateFlow<Boolean> = _isPlaying

    private val _currentTrack = MutableStateFlow<SongResponse?>(null)
    val currentTrack: StateFlow<SongResponse?> = _currentTrack

    private val _currentTrackTitle = MutableStateFlow<String?>(null)
    val currentTrackTitle: StateFlow<String?> = _currentTrackTitle

    private val _currentArtistName = MutableStateFlow<String?>(null)
    val currentArtistName: StateFlow<String?> = _currentArtistName

    private val _currentAlbumArt = MutableStateFlow<String?>(null)
    val currentAlbumArt: StateFlow<String?> = _currentAlbumArt

    private val _currentPosition = MutableStateFlow(0L)
    val currentPosition: StateFlow<Long> = _currentPosition

    private val _duration = MutableStateFlow(0L)
    val duration: StateFlow<Long> = _duration

    // ── Queue / playlist state ─────────────────────────────────────────────────
    private val queueEntries = mutableListOf<Pair<SongResponse, String>>()
    private var currentIndex: Int = -1

    // ── Shuffle / Repeat state ─────────────────────────────────────────────────
    private val _isShuffleOn = MutableStateFlow(false)
    val isShuffleOn: StateFlow<Boolean> = _isShuffleOn

    private var shuffleOrder: MutableList<Int> = mutableListOf()
    private var shufflePosition: Int = -1

    enum class RepeatMode { OFF, ONE, ALL }

    private val _repeatMode = MutableStateFlow(RepeatMode.OFF)
    val repeatMode: StateFlow<RepeatMode> = _repeatMode

    // ── Position updater ──────────────────────────────────────────────────────
    private val handler = Handler(Looper.getMainLooper())
    private val positionUpdater = object : Runnable {
        override fun run() {
            exoPlayer?.let { player ->
                _currentPosition.value = player.currentPosition.coerceAtLeast(0)
                _duration.value = player.duration.coerceAtLeast(0)
            }
            handler.postDelayed(this, 500)
        }
    }

    // ── Initialization ────────────────────────────────────────────────────────
    fun initialize(context: Context, userId: String = "") {
        if (exoPlayer != null) {
            telemetryListener?.updateUserId(userId)
            return
        }

        // Initialize telemetry listener
        telemetryListener = PlaybackTelemetryListener(userId) { event ->
            TelemetryRepository.enqueue(event)
        }

        exoPlayer = ExoPlayer.Builder(context.applicationContext).build().apply {
            playWhenReady = true
            
            // Existing UI & loop state listener
            addListener(object : Player.Listener {
                override fun onIsPlayingChanged(isPlaying: Boolean) {
                    _isPlaying.value = isPlaying
                    if (isPlaying) {
                        handler.post(positionUpdater)
                    } else {
                        handler.removeCallbacks(positionUpdater)
                    }
                }

                override fun onPlaybackStateChanged(playbackState: Int) {
                    if (playbackState == Player.STATE_ENDED) {
                        handler.post {
                            when (_repeatMode.value) {
                                RepeatMode.ONE -> {
                                    exoPlayer?.seekTo(0)
                                    exoPlayer?.play()
                                }
                                else -> skipToNext()
                            }
                        }
                    }
                }
            })

            // Attach telemetry listener to ExoPlayer
            addListener(telemetryListener!!)
        }
    }

    // ── State helpers ─────────────────────────────────────────────────────────
    fun setCurrentTrackLiked(liked: Boolean) {
        _currentTrack.value = _currentTrack.value?.copy(liked = liked)
        val idx = currentIndex
        if (idx in queueEntries.indices) {
            val (song, url) = queueEntries[idx]
            queueEntries[idx] = song.copy(liked = liked) to url
        }
    }

    // ── Queue management ──────────────────────────────────────────────────────
    fun setQueueAndPlay(songs: List<Pair<SongResponse, String>>, startIndex: Int = 0) {
        if (songs.isEmpty()) return

        queueEntries.clear()
        queueEntries.addAll(songs)
        currentIndex = startIndex.coerceIn(0, songs.size - 1)

        if (_isShuffleOn.value) buildShuffleOrder() else clearShuffleState()

        val (song, url) = queueEntries[currentIndex]
        playTrackInternal(song, url)
    }

    // ── Navigation ────────────────────────────────────────────────────────────
    fun skipToNext() {
        if (queueEntries.isEmpty()) return

        val newIndex: Int = if (_isShuffleOn.value && shuffleOrder.isNotEmpty()) {
            shufflePosition = (shufflePosition + 1) % shuffleOrder.size
            shuffleOrder[shufflePosition]
        } else {
            when {
                _repeatMode.value == RepeatMode.ALL -> (currentIndex + 1) % queueEntries.size
                currentIndex < queueEntries.size - 1 -> currentIndex + 1
                else -> return
            }
        }

        currentIndex = newIndex
        val (song, url) = queueEntries[currentIndex]
        playTrackInternal(song, url)
    }

    fun skipToPrevious() {
        if (queueEntries.isEmpty()) return

        if (_currentPosition.value > 3_000L) {
            exoPlayer?.seekTo(0)
            _currentPosition.value = 0L
            return
        }

        val newIndex: Int = if (_isShuffleOn.value && shuffleOrder.isNotEmpty()) {
            shufflePosition = ((shufflePosition - 1) + shuffleOrder.size) % shuffleOrder.size
            shuffleOrder[shufflePosition]
        } else {
            when {
                _repeatMode.value == RepeatMode.ALL -> ((currentIndex - 1) + queueEntries.size) % queueEntries.size
                currentIndex > 0 -> currentIndex - 1
                else -> return
            }
        }

        currentIndex = newIndex
        val (song, url) = queueEntries[currentIndex]
        playTrackInternal(song, url)
    }

    // ── Shuffle / Repeat ──────────────────────────────────────────────────────
    fun toggleShuffle() {
        _isShuffleOn.value = !_isShuffleOn.value
        if (_isShuffleOn.value) {
            buildShuffleOrder()
        } else {
            clearShuffleState()
        }
    }

    fun cycleRepeatMode() {
        _repeatMode.value = when (_repeatMode.value) {
            RepeatMode.OFF -> RepeatMode.ALL
            RepeatMode.ALL -> RepeatMode.ONE
            RepeatMode.ONE -> RepeatMode.OFF
        }
    }

    private fun buildShuffleOrder() {
        if (queueEntries.isEmpty()) return
        val indices = queueEntries.indices.toMutableList()
        indices.shuffle()
        val curPos = indices.indexOf(currentIndex)
        if (curPos > 0) {
            indices.removeAt(curPos)
            indices.add(0, currentIndex)
        }
        shuffleOrder = indices
        shufflePosition = 0
    }

    private fun clearShuffleState() {
        shuffleOrder = mutableListOf()
        shufflePosition = -1
    }

    // ── Core ExoPlayer play ───────────────────────────────────────────────────
    @OptIn(UnstableApi::class)
    fun playTrack(song: SongResponse, url: String) {
        queueEntries.clear()
        queueEntries.add(song to url)
        currentIndex = 0
        clearShuffleState()
        playTrackInternal(song, url)
    }

    private fun playTrackInternal(song: SongResponse, url: String) {
        // Notify telemetry of the new track
        telemetryListener?.onTrackLoaded(song)

        exoPlayer?.let { player ->
            val artworkUri = song.thumbnailUrl
                ?.takeIf { it.isNotBlank() }
                ?.let { Uri.parse(it) }

            val mediaMetadata = MediaMetadata.Builder()
                .setTitle(song.title)
                .setArtist(song.artistName)
                .setArtworkUri(artworkUri)
                .build()

            val mediaItem = MediaItem.Builder()
                .setUri(url)
                .setMediaMetadata(mediaMetadata)
                .build()

            player.setMediaItem(mediaItem)
            player.prepare()
            player.play()

            _currentTrack.value = song
            _currentTrackTitle.value = song.title
            _currentArtistName.value = song.artistName?.ifBlank { "Unknown Artist" } ?: "Unknown Artist"
            _currentAlbumArt.value = song.thumbnailUrl?.takeIf { it.isNotBlank() }
            _currentPosition.value = 0L
            _duration.value = 0L
        }
    }

    // ── Basic controls ────────────────────────────────────────────────────────
    fun togglePlayPause() {
        exoPlayer?.let { if (it.isPlaying) it.pause() else it.play() }
    }

    fun seekTo(positionMs: Long) {
        exoPlayer?.seekTo(positionMs)
        _currentPosition.value = positionMs
    }

    fun release() {
        handler.removeCallbacks(positionUpdater)
        exoPlayer?.release()
        exoPlayer = null
    }
}