package com.mformusic.frontend.data.local

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "downloaded_songs")
data class DownloadedSong(
    @PrimaryKey
    val externalTrackId: String,
    val title: String,
    val artistName: String?,
    val durationInSeconds: Int,
    val thumbnailUrl: String?,
    val saavnUrl: String,
    val s3Url: String?,
    val localFilePath: String,
    val downloadedAt: Long = System.currentTimeMillis()
)
