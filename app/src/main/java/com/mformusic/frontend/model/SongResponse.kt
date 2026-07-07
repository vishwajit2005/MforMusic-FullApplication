package com.mformusic.frontend.model

import com.google.gson.annotations.SerializedName

data class SongResponse(
    val id: Long?,                      // Null for external (unsaved) JioSaavn results
    val externalTrackId: String,
    val title: String,
    val artistName: String?,            // Now populated from JioSaavn
    val durationInSeconds: Int,
    val thumbnailUrl: String?,
    val s3Url: String?,
    val saavnUrl: String,
    val playCount: Int,
    @SerializedName("storedInS3")
    val isStoredInS3: Boolean,
    val liked: Boolean = false
)