# Donetick Homeassistant Integration

This integration connects Home Assistant to Donetick. and Add a Homeassistant Todo so user can view the current tasks in homeasssitant and mark them as complete!

> [!NOTE]  
> When a task is marked as completed, it's assumed that the user who generated the API token used in the integration is the one who completed it.  This integration doesn't currently track different Home Assistant users completing tasks. this will work only from Version 0.1.35 and above 


### Installation
#### Via HACS
- Open HACS in Home Assistant.
- Navigate to Integrations.
- Click on the 3 dots then `Custom repositories`:
    - for Repository use the link of this repo `https://github.com/donetick/donetick-hass-integration/`
    - Type is Integration
- Search for Donetick and click Download.
- Restart Home Assistant.


### Configration: 
The integration can be configure from Homeassistant Integrations. you need to provide donetick URL `https://api.donetick.com` if you are using the cloud version or you url for the selfhosted and make sure to append the port(default donetick is 2021) `http://you-ip-or-host:2021` 
