const projectLabel = "com.docker.compose.project";
const serviceLabel = "com.docker.compose.service";
const services = ["nginx", "web-app", "backend", "auth-api", "recommendation-service"];

function projectFilter() {
    const label = projectLabel + "=" + process.env.COMPOSE_PROJECT_NAME;
    return encodeURIComponent(JSON.stringify({ label: [label] }));
}

async function container(request) {
    const uri = request.uri;
    const query = request.variables.args;
    const inspectUri = uri.replace(/\/logs$/, "/json");
    const response = await request.subrequest("/inspect" + inspectUri);
    if (response.status !== 200) {
        return request.return(response.status);
    }

    let info;
    try {
        info = JSON.parse(response.responseText);
    } catch (error) {
        return request.return(502);
    }

    const project = process.env.COMPOSE_PROJECT_NAME;
    const labels = info.Config && info.Config.Labels;
    if (!project || !labels || labels[projectLabel] !== project ||
        !services.includes(labels[serviceLabel])) {
        return request.return(404);
    }
    if (uri.endsWith("/logs")) {
        return request.internalRedirect("/logs" + uri + (query ? "?" + query : ""));
    }

    request.headersOut["Content-Type"] = "application/json";
    request.return(200, JSON.stringify({
        Config: { Tty: info.Config.Tty },
        State: { Running: info.State.Running, FinishedAt: info.State.FinishedAt },
    }));
}

export default { projectFilter, container };
