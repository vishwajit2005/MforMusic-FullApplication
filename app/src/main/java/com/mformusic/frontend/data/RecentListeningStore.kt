package com.mformusic.frontend.data

import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import com.google.gson.Gson
import kotlinx.coroutines.flow.first

/** Ordered, account-scoped playback history: newest/current plus four previous IDs. */
class RecentListeningStore(private val store: DataStore<Preferences>) {
    private val gson = Gson()
    private fun key(userId: Long) = stringPreferencesKey("recent_played_ids_$userId")

    private fun decode(value: String?): List<String> = try {
        gson.fromJson(value ?: "[]", Array<String>::class.java)?.toList().orEmpty()
            .filter { it.isNotBlank() }.distinct().take(5)
    } catch (_: Exception) { emptyList() }

    suspend fun read(userId: Long): List<String> = decode(store.data.first()[key(userId)])

    suspend fun record(userId: Long, songId: String): List<String> {
        require(songId.isNotBlank())
        var result = emptyList<String>()
        // DataStore serializes concurrent read-modify-write operations.
        store.edit { preferences ->
            result = (listOf(songId) + decode(preferences[key(userId)]))
                .distinct().take(5)
            preferences[key(userId)] = gson.toJson(result)
        }
        return result
    }

    companion object {
        fun context(history: List<String>, currentId: String): List<String> =
            history.filter { it != currentId }.distinct().take(4)
    }
}
