package com.mformusic.frontend.data

import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import com.google.gson.Gson
import com.mformusic.frontend.model.SongResponse
import kotlinx.coroutines.flow.first

/** Last non-empty For You feed, isolated by account and API environment. */
class RecommendationStore(private val store: DataStore<Preferences>, private val environment: String) {
    private val gson = Gson()
    private fun key(userId: Long) = stringPreferencesKey("for_you_v1_${environment}_$userId")
    suspend fun read(userId: Long): List<SongResponse> {
        val raw = store.data.first()[key(userId)] ?: return emptyList()
        return try {
            gson.fromJson(raw, Array<SongResponse>::class.java).orEmpty()
                .filter { !it.externalTrackId.isNullOrBlank() && !it.title.isNullOrBlank() }
                .distinctBy { it.externalTrackId }.take(50)
        } catch (_: Exception) { emptyList() }
    }
    suspend fun save(userId: Long, songs: List<SongResponse>) {
        if (songs.isEmpty()) return // An empty refresh must not erase the last successful feed.
        store.edit { it[key(userId)] = gson.toJson(songs.distinctBy { it.externalTrackId }.take(50)) }
    }
}
