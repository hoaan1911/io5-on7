#include <stdint.h>

/* Samsung Galaxy J7 Prime (Exynos 7870) Hardware Definitions */

#define FB_BASE 0x67000000
#define GIC_DIST 0x104E1000
#define GIC_REDIST 0x104E2000

void platform_init(void) {
    // The shim will use this to set up the display and interrupts
    // before handing off to the XNU kernel.
}
