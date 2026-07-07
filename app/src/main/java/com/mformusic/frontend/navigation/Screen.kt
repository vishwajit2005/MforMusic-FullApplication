package com.mformusic.frontend.navigation

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Search
import androidx.compose.ui.graphics.vector.ImageVector

sealed class Screen(val route: String, val title: String, val icon: ImageVector? = null) {
    // ── Auth flow ─────────────────────────────────────────────────────────────
    object Splash : Screen("splash", "Splash")
    object Login : Screen("login", "Login")
    object Register : Screen("register", "Register")

    // ── Main app (bottom nav) ─────────────────────────────────────────────────
    object Home : Screen("home", "Home", Icons.Default.Home)
    object Search : Screen("search", "Search", Icons.Default.Search)
    object Profile : Screen("profile", "Profile", Icons.Default.Person)
    object LikedSongs : Screen("liked_songs", "Liked Songs")
    object DownloadedSongs : Screen("downloaded_songs", "Downloaded Songs")
}

// Bottom nav items used in NavigationBar
val bottomNavItems = listOf(Screen.Home, Screen.Search, Screen.Profile)