package com.mformusic.frontend.data

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.longPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map

// Extension property for DataStore — single instance per app process
val Context.dataStore: DataStore<Preferences> by preferencesDataStore(name = "mformusic_prefs")

private object PrefKeys {
    val TOKEN = stringPreferencesKey("auth_token")
    val USERNAME = stringPreferencesKey("username")
    val EMAIL = stringPreferencesKey("email")
    val USER_ID = longPreferencesKey("user_id")
}

class TokenDataStore(private val context: Context) {

    val tokenFlow: Flow<String?> = context.dataStore.data.map { it[PrefKeys.TOKEN] }
    val usernameFlow: Flow<String?> = context.dataStore.data.map { it[PrefKeys.USERNAME] }
    val emailFlow: Flow<String?> = context.dataStore.data.map { it[PrefKeys.EMAIL] }

    suspend fun saveAuthData(token: String, username: String, email: String, userId: Long) {
        context.dataStore.edit { prefs ->
            prefs[PrefKeys.TOKEN] = token
            prefs[PrefKeys.USERNAME] = username
            prefs[PrefKeys.EMAIL] = email
            prefs[PrefKeys.USER_ID] = userId
        }
    }

    suspend fun getToken(): String? = context.dataStore.data.first()[PrefKeys.TOKEN]
    suspend fun getUsername(): String? = context.dataStore.data.first()[PrefKeys.USERNAME]
    suspend fun getEmail(): String? = context.dataStore.data.first()[PrefKeys.EMAIL]

    suspend fun clearAuthData() {
        context.dataStore.edit { it.clear() }
    }

    suspend fun hasToken(): Boolean = !getToken().isNullOrBlank()

    suspend fun getUserId(): Long? = context.dataStore.data.first()[PrefKeys.USER_ID]
}
