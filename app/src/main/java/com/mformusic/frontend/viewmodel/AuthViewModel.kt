package com.mformusic.frontend.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.mformusic.frontend.data.TokenDataStore
import com.mformusic.frontend.model.LoginRequest
import com.mformusic.frontend.model.RegisterRequest
import com.mformusic.frontend.network.RetrofitClient
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed class AuthUiState {
    object Idle : AuthUiState()
    object Loading : AuthUiState()
    data class Success(val username: String) : AuthUiState()
    data class Error(val message: String) : AuthUiState()
}

class AuthViewModel(private val tokenDataStore: TokenDataStore) : ViewModel() {

    private val _uiState = MutableStateFlow<AuthUiState>(AuthUiState.Idle)
    val uiState: StateFlow<AuthUiState> = _uiState.asStateFlow()

    private val api = RetrofitClient.musicApiService

    fun login(email: String, password: String) {
        if (email.isBlank() || password.isBlank()) {
            _uiState.value = AuthUiState.Error("Please fill in all fields")
            return
        }
        viewModelScope.launch {
            _uiState.value = AuthUiState.Loading
            try {
                val response = api.login(LoginRequest(email.trim(), password))
                if (response.isSuccessful && response.body() != null) {
                    val auth = response.body()!!
                    tokenDataStore.saveAuthData(auth.token, auth.username, auth.email, auth.userId)
                    _uiState.value = AuthUiState.Success(auth.username)
                } else {
                    val msg = response.errorBody()?.string()?.let {
                        // Strip JSON wrapper if present
                        it.removePrefix("{\"error\":\"").removeSuffix("\"}")
                    } ?: "Login failed. Please try again."
                    _uiState.value = AuthUiState.Error(msg)
                }
            } catch (e: Exception) {
                _uiState.value = AuthUiState.Error("Cannot connect to server. Is the backend running?")
            }
        }
    }

    fun register(username: String, email: String, password: String) {
        if (username.isBlank() || email.isBlank() || password.isBlank()) {
            _uiState.value = AuthUiState.Error("Please fill in all fields")
            return
        }
        if (password.length < 6) {
            _uiState.value = AuthUiState.Error("Password must be at least 6 characters")
            return
        }
        viewModelScope.launch {
            _uiState.value = AuthUiState.Loading
            try {
                val response = api.register(RegisterRequest(username.trim(), email.trim(), password))
                if (response.isSuccessful && response.body() != null) {
                    val auth = response.body()!!
                    tokenDataStore.saveAuthData(auth.token, auth.username, auth.email, auth.userId)
                    _uiState.value = AuthUiState.Success(auth.username)
                } else {
                    val msg = response.errorBody()?.string()?.let {
                        it.removePrefix("{\"error\":\"").removeSuffix("\"}")
                    } ?: "Registration failed. Please try again."
                    _uiState.value = AuthUiState.Error(msg)
                }
            } catch (e: Exception) {
                _uiState.value = AuthUiState.Error("Cannot connect to server. Is the backend running?")
            }
        }
    }

    fun resetState() {
        _uiState.value = AuthUiState.Idle
    }

    companion object {
        fun factory(tokenDataStore: TokenDataStore): ViewModelProvider.Factory =
            object : ViewModelProvider.Factory {
                @Suppress("UNCHECKED_CAST")
                override fun <T : ViewModel> create(modelClass: Class<T>): T =
                    AuthViewModel(tokenDataStore) as T
            }
    }
}
