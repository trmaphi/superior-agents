import axios from 'axios'; // or use axios

export async function getAgentSession(agent_id: string, session_id: string) {
    const apiUrl = 'https://superior-crud-api.fly.dev/api_v1/agent_sessions/get_v2';
    const requestBody = {
        agent_id,
        session_id
    };

    try {
        const response = await axios.post(apiUrl, requestBody, {
            headers: {
                'Content-Type': 'application/json',
                'x-api-key': 'ccm2q324t1qv1eulq894'
            }
        });

        console.log('API Response:', response.data);
        return response.data;
    } catch (error) {
        console.error('Error calling agent_session/get_v2:', error);
        throw new Error(error instanceof Error ? error.message : 'Unknown error');
    }
}

export async function updateAgentSession(agent_id: string, session_id: string, status: string) {
    const apiUrl = 'https://superior-crud-api.fly.dev/api_v1/agent_sessions/update';
    const requestBody = {
        agent_id,
        session_id,
        status
    };

    try {
        const response = await axios.post(apiUrl, requestBody, {
            headers: {
                'Content-Type': 'application/json',
                'x-api-key': 'ccm2q324t1qv1eulq894'
            }
        });

        console.log('API Response:', response.data);
        return response.data;
    } catch (error) {
        console.error('Error calling agent_session/get_v2:', error);
        throw new Error(error instanceof Error ? error.message : 'Unknown error');
    }
}

