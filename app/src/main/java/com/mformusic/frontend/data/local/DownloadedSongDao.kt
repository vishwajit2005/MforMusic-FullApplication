package com.mformusic.frontend.data.local

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

@Dao
interface DownloadedSongDao {
    @Query("SELECT * FROM downloaded_songs ORDER BY downloadedAt DESC")
    fun getAllDownloadedSongs(): Flow<List<DownloadedSong>>

    @Query("SELECT * FROM downloaded_songs WHERE externalTrackId = :externalTrackId LIMIT 1")
    suspend fun getDownloadedSong(externalTrackId: String): DownloadedSong?

    @Query("SELECT * FROM downloaded_songs WHERE externalTrackId = :externalTrackId LIMIT 1")
    fun getDownloadedSongFlow(externalTrackId: String): Flow<DownloadedSong?>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertDownloadedSong(song: DownloadedSong)

    @Query("DELETE FROM downloaded_songs WHERE externalTrackId = :externalTrackId")
    suspend fun deleteDownloadedSong(externalTrackId: String)
}
