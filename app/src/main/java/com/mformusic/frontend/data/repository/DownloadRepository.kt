package com.mformusic.frontend.data.repository

import android.content.Context
import com.mformusic.frontend.data.local.AppDatabase
import com.mformusic.frontend.data.local.DownloadedSong
import com.mformusic.frontend.model.SongResponse
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.io.FileOutputStream

object DownloadRepository {
    private val _downloadingTracks = MutableStateFlow<Set<String>>(emptySet())
    val downloadingTracks: StateFlow<Set<String>> = _downloadingTracks.asStateFlow()

    private val client = OkHttpClient()

    fun isDownloading(externalTrackId: String): Boolean {
        return _downloadingTracks.value.contains(externalTrackId)
    }

    suspend fun downloadSong(context: Context, song: SongResponse): Boolean {
        val externalTrackId = song.externalTrackId
        if (isDownloading(externalTrackId)) return false

        _downloadingTracks.value = _downloadingTracks.value + externalTrackId

        val streamUrl = song.s3Url ?: song.saavnUrl
        if (streamUrl.isBlank()) {
            _downloadingTracks.value = _downloadingTracks.value - externalTrackId
            return false
        }

        return withContext(Dispatchers.IO) {
            try {
                val downloadDir = File(context.filesDir, "downloads")
                if (!downloadDir.exists()) {
                    downloadDir.mkdirs()
                }
                val destinationFile = File(downloadDir, "${externalTrackId}.mp3")

                val request = Request.Builder().url(streamUrl).build()
                val response = client.newCall(request).execute()
                if (!response.isSuccessful) {
                    _downloadingTracks.value = _downloadingTracks.value - externalTrackId
                    return@withContext false
                }

                val body = response.body
                if (body == null) {
                    _downloadingTracks.value = _downloadingTracks.value - externalTrackId
                    return@withContext false
                }

                body.byteStream().use { inputStream ->
                    FileOutputStream(destinationFile).use { outputStream ->
                        val data = ByteArray(8192)
                        var count: Int
                        while (inputStream.read(data).also { count = it } != -1) {
                            outputStream.write(data, 0, count)
                        }
                        outputStream.flush()
                    }
                }

                // Save to Room DB
                val downloadedSong = DownloadedSong(
                    externalTrackId = externalTrackId,
                    title = song.title,
                    artistName = song.artistName,
                    durationInSeconds = song.durationInSeconds,
                    thumbnailUrl = song.thumbnailUrl,
                    saavnUrl = song.saavnUrl,
                    s3Url = song.s3Url,
                    localFilePath = destinationFile.absolutePath
                )
                AppDatabase.getDatabase(context).downloadedSongDao().insertDownloadedSong(downloadedSong)
                true
            } catch (e: Exception) {
                e.printStackTrace()
                false
            } finally {
                _downloadingTracks.value = _downloadingTracks.value - externalTrackId
            }
        }
    }

    suspend fun deleteSong(context: Context, externalTrackId: String) {
        withContext(Dispatchers.IO) {
            try {
                val dao = AppDatabase.getDatabase(context).downloadedSongDao()
                val song = dao.getDownloadedSong(externalTrackId)
                if (song != null) {
                    dao.deleteDownloadedSong(externalTrackId)
                    val file = File(song.localFilePath)
                    if (file.exists()) {
                        file.delete()
                    }
                }
            } catch (e: Exception) {
                e.printStackTrace()
            }
        }
    }
}
