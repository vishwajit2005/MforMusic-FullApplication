package com.mformusic.frontend.telemetry

import androidx.media3.common.Player
import com.mformusic.frontend.model.SongResponse

class PlaybackTelemetryListener(
    private var userId: String,
    private val onEvent: (TelemetryEvent) -> Unit
) : Player.Listener {

    private var currentSong: SongResponse? = null
    private var playStartWallClock: Long = 0L
    private var accumulatedPlayMs: Long = 0L
    private var isCurrentlyPlaying: Boolean = false
    private val playedTrackIdsInSession = mutableSetOf<String>()

    fun updateUserId(newUserId: String) {
        this.userId = newUserId
    }

    fun onTrackLoaded(song: SongResponse) {
        currentSong?.let { prev ->
            if (isCurrentlyPlaying) {
                accumulatedPlayMs += System.currentTimeMillis() - playStartWallClock
            }
            emitPlayOrSkip(prev, accumulatedPlayMs)
        }

        currentSong = song
        accumulatedPlayMs = 0L
        isCurrentlyPlaying = false
        playStartWallClock = 0L
    }

    override fun onIsPlayingChanged(isPlaying: Boolean) {
        val now = System.currentTimeMillis()
        if (isPlaying && !isCurrentlyPlaying) {
            playStartWallClock = now
            isCurrentlyPlaying = true
        } else if (!isPlaying && isCurrentlyPlaying) {
            accumulatedPlayMs += now - playStartWallClock
            isCurrentlyPlaying = false
        }
    }

    override fun onPlaybackStateChanged(playbackState: Int) {
        if (playbackState == Player.STATE_ENDED) {
            if (isCurrentlyPlaying) {
                accumulatedPlayMs += System.currentTimeMillis() - playStartWallClock
                isCurrentlyPlaying = false
            }
            currentSong?.let { song ->
                val totalMs = song.durationInSeconds * 1000L
                val completionRate = if (totalMs > 0) accumulatedPlayMs.toFloat() / totalMs else 1f
                val durationSec = (accumulatedPlayMs / 1000).toInt()
                emitEvent(
                    song = song,
                    type = InteractionType.PLAY.name.lowercase(),
                    durationSec = durationSec,
                    completionRate = completionRate.coerceIn(0f, 1f)
                )
                playedTrackIdsInSession.add(song.externalTrackId)
            }
        }
    }

    private fun emitPlayOrSkip(song: SongResponse, listenedMs: Long) {
        val totalMs = song.durationInSeconds * 1000L
        val listenedSec = (listenedMs / 1000).toInt()
        val completionRate = if (totalMs > 0) listenedMs.toFloat() / totalMs else 0f

        val type = if (listenedSec < 30 || completionRate < 0.30f) {
            InteractionType.SKIP.name.lowercase()
        } else {
            playedTrackIdsInSession.add(song.externalTrackId)
            InteractionType.PLAY.name.lowercase()
        }

        emitEvent(song, type, listenedSec, completionRate.coerceIn(0f, 1f))
    }

    private fun emitEvent(
        song: SongResponse,
        type: String,
        durationSec: Int,
        completionRate: Float
    ) {
        if (userId.isBlank()) return // Avoid sending unauthenticated events

        onEvent(
            TelemetryEvent(
                userId = userId,
                songId = song.externalTrackId,
                interactionType = type,
                playDurationSec = durationSec,
                completionRate = completionRate,
                sessionId = SessionManager.sessionId
            )
        )
    }
}