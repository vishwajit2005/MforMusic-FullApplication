package com.mformusic.backend;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@org.springframework.test.context.ActiveProfiles("capacity")
@org.springframework.context.annotation.Import(com.mformusic.backend.capacity.CapacityTestConfig.class)
@SpringBootTest(properties={"capacity.seed-users=5", "capacity.seed-songs=30"})
class BackendApplicationTests {

	@Test
	void contextLoads() {
	}

}
