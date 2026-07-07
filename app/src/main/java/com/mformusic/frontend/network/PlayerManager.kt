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
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

object PlayerManager {

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
    /**
     * The ordered queue. Each entry is (SongResponse, resolvedStreamUrl).
     * The URL is already resolved so next/prev can play immediately without
     * any async API call.
     */
    private val queueEntries = mutableListOf<Pair<SongResponse, String>>()

    /** Index of the currently playing track inside [queueEntries]. -1 means no queue. */
    private var currentIndex: Int = -1

    // ── Shuffle / Repeat state ─────────────────────────────────────────────────
    private val _isShuffleOn = MutableStateFlow(false)
    val isShuffleOn: StateFlow<Boolean> = _isShuffleOn

    /**
     * When shuffle is on, this list holds the shuffled order of queue indices.
     * shufflePosition tracks where we are inside this list.
     */
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
                _duration.value    = player.duration.coerceAtLeast(0)
            }
            handler.postDelayed(this, 500)
        }
    }

    // ── Initialization ────────────────────────────────────────────────────────

    fun initialize(context: Context) {
        if (exoPlayer != null) return
        exoPlayer = ExoPlayer.Builder(context.applicationContext).build().apply {
            playWhenReady = true
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
                        // Run on the main looper to avoid calling ExoPlayer methods
                        // from inside its own callback stack.
                        handler.post {
                            when (_repeatMode.value) {
                                RepeatMode.ONE -> {
                                    exoPlayer?.seekTo(0)
                                    exoPlayer?.play()
                                }
                                // For OFF and ALL: always try to advance.
                                // If we're at the last song and repeat is OFF,
                                // skipToNext() will handle that gracefully.
                                else -> skipToNext()
                            }
                        }
                    }
                }
            })
        }
    }

    // ── State helpers ─────────────────────────────────────────────────────────

    fun setCurrentTrackLiked(liked: Boolean) {
        _currentTrack.value = _currentTrack.value?.copy(liked = liked)
        // Also update in the queue so the liked state is consistent
        val idx = currentIndex
        if (idx in queueEntries.indices) {
            val (song, url) = queueEntries[idx]
            queueEntries[idx] = song.copy(liked = liked) to url
        }
    }

    // ── Queue management ──────────────────────────────────────────────────────

    /**
     * Set the queue and immediately start playing [startIndex].
     *
     * @param songs      List of (SongResponse, resolvedStreamUrl) pairs — URLs must
     *                   be pre-resolved (HTTP/HTTPS or local file URI).
     * @param startIndex Position to begin playback at.
     */
    fun setQueueAndPlay(songs: List<Pair<SongResponse, String>>, startIndex: Int = 0) {
        if (songs.isEmpty()) return

        queueEntries.clear()
        queueEntries.addAll(songs)

        currentIndex = startIndex.coerceIn(0, songs.size - 1)

        // Rebuild shuffle order if shuffle is currently on
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
                _repeatMode.value == RepeatMode.ALL ->
                    (currentIndex + 1) % queueEntries.size
                currentIndex < queueEntries.size - 1 ->
                    currentIndex + 1
                else -> return  // Last song, no repeat
            }
        }

        currentIndex = newIndex
        val (song, url) = queueEntries[currentIndex]
        playTrackInternal(song, url)
    }

    fun skipToPrevious() {
        if (queueEntries.isEmpty()) return

        // If we're more than 3 seconds in, restart the current track instead
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
                _repeatMode.value == RepeatMode.ALL ->
                    ((currentIndex - 1) + queueEntries.size) % queueEntries.size
                currentIndex > 0 ->
                    currentIndex - 1
                else -> return  // First song, no repeat back
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
        // Keep currently-playing song at position 0 in the shuffle order
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
        // Public version — used by legacy callers that don't set a queue.
        // Wraps the song in a single-item queue so next/prev at least work
        // predictably (they'll just do nothing or restart).
        queueEntries.clear()
        queueEntries.add(song to url)
        currentIndex = 0
        clearShuffleState()
        playTrackInternal(song, url)
    }

    private fun playTrackInternal(song: SongResponse, url: String) {
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

            // Update exposed state immediately
            _currentTrack.value    = song
            _currentTrackTitle.value = song.title
            _currentArtistName.value = song.artistName
                ?.ifBlank { "Unknown Artist" } ?: "Unknown Artist"
            _currentAlbumArt.value = song.thumbnailUrl?.takeIf { it.isNotBlank() }
            _currentPosition.value = 0L
            _duration.value        = 0L
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