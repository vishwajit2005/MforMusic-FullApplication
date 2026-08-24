package com.mformusic.frontend.telemetry

import com.google.gson.annotations.SerializedName

enum class InteractionType {
    @SerializedName("play")
    PLAY,
    @SerializedName("skip")
    SKIP,
    @SerializedName("like")
    LIKE,
    @SerializedName("unlike")
    UNLIKE,
    @SerializedName("playlist_add")
    PLAYLIST_ADD,
    @SerializedName("download")
    DOWNLOAD
}

data class TelemetryEvent(
    @SerializedName("user_id")
    val userId: String,
    @SerializedName("song_id")
    val songId: String, // externalTrackId (JioSaavn ID)
    @SerializedName("interaction_type")
    val interactionType: String,
    @SerializedName("play_duration_sec")
    val playDurationSec: Int = 0,
    @SerializedName("completion_rate")
    val completionRate: Float = 0f,
    @SerializedName("session_id")
    val sessionId: String,
    @SerializedName("device_timestamp")
    val deviceTimestamp: Long = System.currentTimeMillis()
)