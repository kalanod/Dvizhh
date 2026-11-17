import { MainLayout } from "../../layouts";
import { EventSection } from "../../widgets";
import { EventDiscoveryMap } from "../../widgets/EventDiscoveryMap/EventDiscoveryMap";
import { useEventDiscovery } from "../../../hooks/useEventDiscovery";
import type { DiscoveryMapItem } from "../../../api/discovery";

const EMPTY_MARKERS: DiscoveryMapItem[] = [];

export const FeedPage = () => {
    const discovery = useEventDiscovery();
    return <MainLayout>
        <div className="flex w-full min-w-0 flex-col gap-5">
            <EventDiscoveryMap key={discovery.userId ?? "guest"}
                initialFilters={discovery.initialFilters} queryFailed={discovery.error !== undefined}
                items={discovery.map?.items ?? EMPTY_MARKERS} total={discovery.map?.total_events ?? 0}
                loading={discovery.loading}
                mapViewport={discovery.mapViewport}
                collapsed={discovery.mapCollapsed} onCollapsedChange={discovery.setMapCollapsed}
                onViewport={discovery.setViewport} onCluster={discovery.selectCluster} onUnavailable={discovery.mapUnavailable} />
            <EventSection title="Афиша" discovery={discovery} />
        </div>
    </MainLayout>;
};
