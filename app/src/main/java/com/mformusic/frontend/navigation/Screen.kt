package com.mformusic.frontend.navigation

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.ui.graphics.vector.ImageVector

sealed class Screen(val route: String, val title: String, val icon: ImageVector? = null) {
    // ── Auth flow ─────────────────────────────────────────────────────────────
    object Splash : Screen("splash", "Splash")
    object Login : Screen("login", "Login")
    object Register : Screen("register", "Register")

    // ── Main app (bottom nav) ─────────────────────────────────────────────────
    object Home   : Screen("home",    "Home",   Icons.Default.Home)
    object ForYou : Screen("for_you", "For You", Icons.Default.AutoAwesome)
    object Search : Screen("search",  "Search",  Icons.Default.Search)
    object Profile : Screen("profile", "Profile", Icons.Default.Person)
    object LikedSongs : Screen("liked_songs", "Liked Songs")
    object DownloadedSongs : Screen("downloaded_songs", "Downloaded Songs")
}

// Bottom nav items — ForYou slot between Home and Search
val bottomNavItems = listOf(Screen.Home, Screen.ForYou, Screen.Search, Screen.Profile)