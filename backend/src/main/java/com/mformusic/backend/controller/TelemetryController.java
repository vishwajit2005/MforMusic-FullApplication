package com.mformusic.backend.controller;

import com.mformusic.backend.dto.TelemetryEventDto;
import com.mformusic.backend.security.UserPrincipal;
import com.mformusic.backend.service.TelemetryService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@Slf4j
@RestController
@RequestMapping("/api/v1/telemetry")
@RequiredArgsConstructor
public class TelemetryController {

    private final TelemetryService telemetryService;

    @PostMapping("/interactions")
    public ResponseEntity<Map<String, Object>> trackInteraction(
            @Valid @RequestBody TelemetryEventDto requestDto,
            Authentication authentication
    ) {
        // Extract authenticated user ID from UserPrincipal
        Long authenticatedUserId = extractUserId(authentication);

        // Prioritize authenticated JWT userId over client payload if available
        if (authenticatedUserId != null) {
            requestDto.setUserId(authenticatedUserId.toString());
        }

        telemetryService.ingestInteraction(requestDto);

        return ResponseEntity.status(HttpStatus.ACCEPTED).body(
                Map.of(
                        "status", "ACCEPTED",
                        "message", "Telemetry event queued for processing"
                )
        );
    }

    private Long extractUserId(Authentication auth) {
        if (auth != null && auth.getPrincipal() instanceof UserPrincipal principal) {
            return principal.userId();
        }
        return null;
    }
}