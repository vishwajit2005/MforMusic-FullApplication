package com.mformusic.frontend.telemetry

import java.util.UUID

object SessionManager {
    val sessionId: String = UUID.randomUUID().toString()
}