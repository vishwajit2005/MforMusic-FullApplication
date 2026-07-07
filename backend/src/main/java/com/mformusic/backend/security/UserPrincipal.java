package com.mformusic.backend.security;

/**
 * Custom principal stored in the Spring SecurityContext after JWT validation.
 * Accessible in any controller via SecurityContextHolder or Authentication.getPrincipal().
 */
public record UserPrincipal(Long userId, String email, String username) {}
