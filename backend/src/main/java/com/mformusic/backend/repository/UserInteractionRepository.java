package com.mformusic.backend.repository;

import com.mformusic.backend.model.UserInteraction;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface UserInteractionRepository extends JpaRepository<UserInteraction, Long> {

    List<UserInteraction> findByUserIdOrderByCreatedAtDesc(String userId, Pageable pageable);

    List<UserInteraction> findBySongIdOrderByCreatedAtDesc(String songId, Pageable pageable);

    long countByUserId(String userId);
}